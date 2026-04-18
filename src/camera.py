"""
camera.py — Webcam capture abstraction with resource management.

Usage
-----
    with CameraCapture(config) as cam:
        while True:
            frame = cam.read()
            if frame is None:
                break
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from src.config import AppConfig

logger = logging.getLogger(__name__)


class CameraCapture:
    """
    Managed webcam capture with minimal-latency configuration.
    Supports ``with`` statement for automatic resource cleanup.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._cap: Optional[cv2.VideoCapture] = None

    # ── Context manager ──────────────────────────────────────────────────
    def __enter__(self) -> "CameraCapture":
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Lifecycle ────────────────────────────────────────────────────────
    def open(self) -> None:
        logger.info("Opening camera %d …", self._config.camera_index)
        self._cap = cv2.VideoCapture(self._config.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera {self._config.camera_index}. "
                "Check device index or permissions."
            )
        # Configure for minimal latency
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.frame_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.frame_height)
        self._cap.set(cv2.CAP_PROP_FPS, self._config.target_fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # no frame queuing

        # Warm up — discard initial dark frames
        for _ in range(8):
            self._cap.read()

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("Camera ready: %dx%d", actual_w, actual_h)

    def close(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
            logger.info("Camera released.")
        self._cap = None

    # ── Frame acquisition ────────────────────────────────────────────────
    def read(self) -> Optional[np.ndarray]:
        """
        Read a single frame, horizontally flipped for mirror effect.
        Returns None on failure.
        """
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret:
            return None
        return cv2.flip(frame, 1)  # mirror for natural feel

    def read_raw(self) -> Optional[np.ndarray]:
        """Read without mirroring (for cases where raw frame is needed)."""
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    @property
    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def get_jpeg_bytes(self, frame: np.ndarray, quality: int = 70) -> bytes:
        """Encode frame as JPEG bytes (for streaming to web)."""
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()
