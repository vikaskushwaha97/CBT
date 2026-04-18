"""
detector.py — MediaPipe 3D pose detection (multi-person).

Extracts **world coordinates** (meters, hip-centered) from MediaPipe,
not normalized screen coordinates.  Uses the Tasks API (MediaPipe 0.10+).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import cv2
import numpy as np

from src.config import AppConfig
from src.models import Landmark3D

logger = logging.getLogger(__name__)


class PoseDetector:
    """
    Multi-person 3D pose detector using MediaPipe Tasks API.

    Returns list[list[Landmark3D]] — one landmark set per person.
    Uses ``pose_world_landmarks`` for real-world meter-scale coordinates.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._init_detector(config)
        logger.info(
            "PoseDetector initialized: num_poses=%d",
            config.num_poses,
        )

    def _init_detector(self, config: AppConfig):
        from mediapipe.tasks.python import vision as vis
        from mediapipe.tasks.python.core import base_options as bo
        from mediapipe import Image as MpImg, ImageFormat as MpFmt

        self._MpImg = MpImg
        self._MpFmt = MpFmt

        model_path = config.model_path
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file not found: {model_path}. "
                "Download pose_landmarker.task from MediaPipe."
            )

        opts = vis.PoseLandmarkerOptions(
            base_options=bo.BaseOptions(
                model_asset_path=os.path.abspath(model_path)
            ),
            num_poses=config.num_poses,
            running_mode=vis.RunningMode.IMAGE,
            min_pose_detection_confidence=config.min_detection_confidence,
            min_tracking_confidence=config.min_tracking_confidence,
        )
        self._det = vis.PoseLandmarker.create_from_options(opts)

    def detect(self, frame_bgr: np.ndarray) -> list[list[Landmark3D]]:
        """
        Detect poses in a BGR frame.

        Returns
        -------
        list[list[Landmark3D]]
            One inner list (33 landmarks) per detected person.
            Empty list if no person detected.
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._det.detect(
            self._MpImg(image_format=self._MpFmt.SRGB, data=rgb)
        )
        persons = []
        for world_lms in (result.pose_world_landmarks or []):
            persons.append([
                Landmark3D(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)
                for lm in world_lms
            ])
        return persons

    def detect_with_screen(self, frame_bgr: np.ndarray):
        """
        Detect poses and return both world + screen landmarks.
        Screen landmarks are needed for drawing overlays on the camera feed.

        Returns
        -------
        tuple[list[list[Landmark3D]], list[list[Landmark3D]]]
            (world_landmarks_per_person, screen_landmarks_per_person)
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._det.detect(
            self._MpImg(image_format=self._MpFmt.SRGB, data=rgb)
        )
        world_persons = []
        screen_persons = []

        world_list = result.pose_world_landmarks or []
        screen_list = result.pose_landmarks or []

        for world_lms in world_list:
            world_persons.append([
                Landmark3D(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)
                for lm in world_lms
            ])
        for screen_lms in screen_list:
            screen_persons.append([
                Landmark3D(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)
                for lm in screen_lms
            ])

        return world_persons, screen_persons

    def close(self):
        self._det.close()
