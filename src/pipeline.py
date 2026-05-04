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
from src.models import (
    FrameResult, Landmark3D, LandmarkIndex as LI,
    PersonData, SensorID, SENSOR_TO_TRACKER, TrackerID,
)
from src.osc_sender import OSCSender
from src.skeleton import SkeletonSolver

logger = logging.getLogger(__name__)


class TrackingPipeline:
    """
    Orchestrates the full tracking chain for N persons per frame.

    In camera-only mode  : Camera → MediaPipe → Filter → Solver → Output
    In hybrid mode       : Camera path as above, then IMU rotations override
                           camera-estimated rotations for equipped body parts.

    Usage
    -----
        pipeline = TrackingPipeline(config)
        pipeline = TrackingPipeline(config, imu_source=imu)  # hybrid
        result = pipeline.process_frame(bgr_frame)
    """

    def __init__(self, config: AppConfig, imu_source=None):
        self._config = config
        self.detector = PoseDetector(config)
        self.solver = SkeletonSolver(config)
        self.calibrator = Calibrator(config)
        self.osc = OSCSender(config)
        self._imu_source = imu_source  # Optional[IMUSource]

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

        mode = config.source_mode if imu_source else "camera"
        logger.info("TrackingPipeline initialized (num_poses=%d, mode=%s)",
                    config.num_poses, mode)

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

            # IMU hybrid: override camera rotations with sensor data (person 0 only)
            if self._imu_source and i == 0:
                trackers = self._apply_imu_rotations(trackers, filtered)

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

        # ── 4. Collect sensor states ─────────────────────────────────────
        sensor_states = self._imu_source.get_all_states() if self._imu_source else []
        imu_active = self._imu_source is not None and self._imu_source.connected_count() > 0

        return FrameResult(
            timestamp=timestamp,
            persons=persons,
            fps=self._fps,
            latency_ms=self._last_latency,
            num_persons=len(persons),
            osc_active=self.osc.is_active,
            calibrated=self.calibrator.is_calibrated,
            imu_active=imu_active,
            sensor_states=sensor_states,
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
        if self._imu_source:
            self._imu_source.stop()
        logger.info("Pipeline closed.")

    # ── IMU Fusion ───────────────────────────────────────────────────────────
    def _apply_imu_rotations(self, trackers: dict, landmarks: list) -> dict:
        """
        Override camera-estimated rotations with IMU sensor data.

        For each connected sensor:
          1. Get corrected (pitch, yaw, roll) from IMUSource (yaw already
             corrected via complementary filter from previous frame)
          2. Replace TrackerData.rotation in the trackers dict
          3. Feed camera-estimated yaw back to IMUSource for next frame
        """
        import math
        from src.models import TrackerData

        for sensor_id_val, tracker_id in SENSOR_TO_TRACKER.items():
            if tracker_id not in trackers:
                continue

            rotation = self._imu_source.get_corrected_rotation(sensor_id_val)
            if rotation is None:
                continue  # sensor not connected — keep camera estimate

            pitch, yaw, roll = rotation
            # Replace rotation only; keep camera-derived position
            old = trackers[tracker_id]
            trackers[tracker_id] = TrackerData(
                position=old.position,
                rotation=(pitch, yaw, roll),
            )

        # Feed camera yaw back for drift correction on hip sensor
        self._feed_camera_yaw(landmarks)
        return trackers

    def _feed_camera_yaw(self, landmarks: list) -> None:
        """
        Estimate hip yaw from MediaPipe shoulder landmarks and send to IMUSource
        so it can correct MPU-6050 yaw drift on the next frame.
        """
        import math
        try:
            ls = landmarks[LI.LEFT_SHOULDER]
            rs = landmarks[LI.RIGHT_SHOULDER]
            if ls.visibility < 0.4 or rs.visibility < 0.4:
                return
            # Shoulder vector in camera world space (X=right, Z=depth)
            dx = rs.x - ls.x
            dz = rs.z - ls.z
            camera_yaw = math.degrees(math.atan2(dz, dx))
            self._imu_source.apply_yaw_correction(SensorID.HIP.value, camera_yaw)
            self._imu_source.apply_yaw_correction(SensorID.CHEST.value, camera_yaw)
        except (IndexError, AttributeError):
            pass
