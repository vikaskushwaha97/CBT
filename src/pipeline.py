"""
pipeline.py — Main processing pipeline orchestrator.

Chains:  Camera Frame → Detector → Filter → Skeleton Solver → Output
Handles multi-person tracking with per-person filter state.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from src.calibration import Calibrator
from src.config import AppConfig
from src.detector import PoseDetector
from src.filters import PoseFilter
from src.models import FrameResult, Landmark3D, PersonData, TrackerID
from src.osc_sender import OSCSender
from src.skeleton import SkeletonSolver

logger = logging.getLogger(__name__)


class TrackingPipeline:
    """
    Orchestrates the full tracking chain for N persons per frame.

    Usage
    -----
        pipeline = TrackingPipeline(config)
        result = pipeline.process_frame(bgr_frame)
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self.detector = PoseDetector(config)
        self.solver = SkeletonSolver(config)
        self.calibrator = Calibrator(config)
        self.osc = OSCSender(config)

        # Per-person filter bank (keyed by person index)
        self._filters: dict[int, PoseFilter] = {}

        # Performance tracking
        self._frame_count = 0
        self._fps_timer = time.time()
        self._fps = 0.0
        self._last_latency = 0.0

        # Try loading existing calibration
        self.calibrator.load()
        if self.calibrator.is_calibrated:
            self.solver.set_calibration(self.calibrator.profile)

        logger.info("TrackingPipeline initialized (num_poses=%d)", config.num_poses)

    def process_frame(self, frame: np.ndarray) -> FrameResult:
        """
        Full processing pipeline for a single camera frame.

        Returns FrameResult with all person data, metrics, and status.
        """
        t_start = time.time()

        # ── 1. Detect poses ──────────────────────────────────────────────
        world_poses, screen_poses = self.detector.detect_with_screen(frame)

        # ── 2. Filter + Solve per person ────────────────────────────────
        persons: list[PersonData] = []
        timestamp = time.time()

        for i, world_lms in enumerate(world_poses):
            # Ensure filter bank exists for this person
            if i not in self._filters:
                self._filters[i] = PoseFilter(
                    n_landmarks=33,
                    freq=self._config.filter_freq,
                    min_cutoff=self._config.filter_min_cutoff,
                    beta=self._config.filter_beta,
                    d_cutoff=self._config.filter_d_cutoff,
                )

            # Apply One-Euro filtering
            filtered = self._filters[i].filter(world_lms, timestamp)

            # Solve skeleton → tracker data
            trackers = self.solver.solve(filtered)

            # Send OSC for primary person only
            if i == 0 and self.osc.is_active:
                self.osc.send_all(trackers)

            # Compute average confidence
            avg_conf = sum(lm.visibility for lm in filtered) / len(filtered) if filtered else 0

            # Use screen landmarks for the person data (for overlay drawing)
            screen_lms = screen_poses[i] if i < len(screen_poses) else filtered

            persons.append(PersonData(
                person_id=i,
                landmarks=screen_lms,  # screen coords for visualization
                trackers=trackers,
                confidence=avg_conf,
            ))

        # Clean up filters for persons no longer tracked
        active_ids = set(range(len(world_poses)))
        stale = [k for k in self._filters if k not in active_ids]
        for k in stale:
            del self._filters[k]

        # ── 3. Performance metrics ───────────────────────────────────────
        self._frame_count += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 0.5:  # update FPS every 500ms
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = time.time()

        self._last_latency = (time.time() - t_start) * 1000  # ms

        return FrameResult(
            timestamp=timestamp,
            persons=persons,
            fps=self._fps,
            latency_ms=self._last_latency,
            num_persons=len(persons),
            osc_active=self.osc.is_active,
            calibrated=self.calibrator.is_calibrated,
        )

    def calibrate(self, landmarks: list[Landmark3D]) -> bool:
        """Trigger T-pose calibration with current landmarks."""
        try:
            profile = self.calibrator.capture_t_pose(landmarks)
            self.solver.set_calibration(profile)
            self.calibrator.save()
            return True
        except Exception as e:
            logger.error("Calibration failed: %s", e)
            return False

    def update_filter_params(self, min_cutoff: float = None, beta: float = None):
        """Live-update filter parameters for all persons."""
        for pf in self._filters.values():
            pf.update_params(min_cutoff=min_cutoff, beta=beta)

    def toggle_osc(self, enabled: bool, ip: str = None, port: int = None) -> bool:
        if enabled:
            return self.osc.enable(ip, port)
        else:
            self.osc.disable()
            return True

    def close(self):
        self.detector.close()
        logger.info("Pipeline closed.")
