"""
calibration.py — T-pose calibration and body proportion measurement.

Captures a reference T-pose to:
  1. Measure body proportions (arm length, leg length, torso, shoulder width)
  2. Compute a scale factor from real height to MediaPipe coordinate space
  3. Determine floor offset so feet sit at Y=0 in VR
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Optional

from src.config import AppConfig
from src.models import CalibrationProfile, Landmark3D, LandmarkIndex as LI

logger = logging.getLogger(__name__)


def _dist3d(a: Landmark3D, b: Landmark3D) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


class Calibrator:
    """
    T-pose calibration for body proportion measurement and coordinate scaling.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._profile: Optional[CalibrationProfile] = None

    @property
    def is_calibrated(self) -> bool:
        return self._profile is not None

    @property
    def profile(self) -> Optional[CalibrationProfile]:
        return self._profile

    def capture_t_pose(self, landmarks: list[Landmark3D]) -> CalibrationProfile:
        """
        Capture reference measurements from a T-pose.

        The user should be standing upright with arms extended horizontally.
        """
        if len(landmarks) < 33:
            raise ValueError("Need 33 landmarks for calibration")

        # Key landmarks
        l_shoulder = landmarks[LI.LEFT_SHOULDER]
        r_shoulder = landmarks[LI.RIGHT_SHOULDER]
        l_hip = landmarks[LI.LEFT_HIP]
        r_hip = landmarks[LI.RIGHT_HIP]
        l_ankle = landmarks[LI.LEFT_ANKLE]
        r_ankle = landmarks[LI.RIGHT_ANKLE]
        l_wrist = landmarks[LI.LEFT_WRIST]
        r_wrist = landmarks[LI.RIGHT_WRIST]
        l_elbow = landmarks[LI.LEFT_ELBOW]
        r_elbow = landmarks[LI.RIGHT_ELBOW]
        nose = landmarks[LI.NOSE]

        # ── Measurements ─────────────────────────────────────────────────
        shoulder_width = _dist3d(l_shoulder, r_shoulder)

        # Arm = shoulder→elbow + elbow→wrist (average both arms)
        l_arm = _dist3d(l_shoulder, l_elbow) + _dist3d(l_elbow, l_wrist)
        r_arm = _dist3d(r_shoulder, r_elbow) + _dist3d(r_elbow, r_wrist)
        arm_length = (l_arm + r_arm) / 2

        # Torso = midpoint shoulders → midpoint hips
        shoulder_mid_y = (l_shoulder.y + r_shoulder.y) / 2
        hip_mid_y = (l_hip.y + r_hip.y) / 2
        torso_length = abs(hip_mid_y - shoulder_mid_y)

        # Legs = hip → ankle (average both legs)
        l_leg = _dist3d(l_hip, l_ankle)
        r_leg = _dist3d(r_hip, r_ankle)
        leg_length = (l_leg + r_leg) / 2

        # Total height estimate: head-top to ankle
        # Nose is ~8% below the top of the head
        mp_height = abs(nose.y * 0.92 - ((l_ankle.y + r_ankle.y) / 2))
        if mp_height < 0.1:
            mp_height = 1.7  # fallback

        # Scale: real height / MediaPipe height
        real_height_m = self._config.user_height_cm / 100.0
        scale_factor = real_height_m / mp_height

        # Floor offset: lowest ankle Y, scaled to Unity
        lowest_ankle_y = max(l_ankle.y, r_ankle.y)  # largest Y = lowest in MediaPipe
        floor_offset = lowest_ankle_y * scale_factor

        # Hip center
        hip_cx = (l_hip.x + r_hip.x) / 2
        hip_cy = (l_hip.y + r_hip.y) / 2
        hip_cz = (l_hip.z + r_hip.z) / 2

        profile = CalibrationProfile(
            user_height_cm=self._config.user_height_cm,
            scale_factor=scale_factor,
            floor_offset_y=floor_offset,
            shoulder_width=shoulder_width * scale_factor,
            arm_length=arm_length * scale_factor,
            leg_length=leg_length * scale_factor,
            torso_length=torso_length * scale_factor,
            hip_center=(hip_cx, hip_cy, hip_cz),
            captured_at=time.time(),
        )

        self._profile = profile
        logger.info(
            "Calibration captured: scale=%.3f, height=%.1fcm, "
            "shoulder=%.2fm, arm=%.2fm, leg=%.2fm, torso=%.2fm",
            scale_factor,
            self._config.user_height_cm,
            profile.shoulder_width,
            profile.arm_length,
            profile.leg_length,
            profile.torso_length,
        )
        return profile

    def apply(self, landmarks: list[Landmark3D]) -> list[Landmark3D]:
        """
        Apply calibration scaling to landmarks.
        If not calibrated, returns landmarks unchanged.
        """
        if not self._profile:
            return landmarks
        # Calibration is applied in the skeleton solver via scale_factor,
        # so we pass through here. This method exists for future use
        # (e.g., proportion-based depth correction).
        return landmarks

    # ── Persistence ──────────────────────────────────────────────────────
    def save(self, path: Optional[str] = None) -> str:
        if not self._profile:
            raise RuntimeError("No calibration to save")
        path = path or self._config.calibration_file
        data = {
            "user_height_cm": self._profile.user_height_cm,
            "scale_factor": self._profile.scale_factor,
            "floor_offset_y": self._profile.floor_offset_y,
            "shoulder_width": self._profile.shoulder_width,
            "arm_length": self._profile.arm_length,
            "leg_length": self._profile.leg_length,
            "torso_length": self._profile.torso_length,
            "hip_center": list(self._profile.hip_center),
            "captured_at": self._profile.captured_at,
        }
        Path(path).write_text(json.dumps(data, indent=2))
        logger.info("Calibration saved → %s", path)
        return path

    def load(self, path: Optional[str] = None) -> bool:
        path = path or self._config.calibration_file
        try:
            data = json.loads(Path(path).read_text())
            self._profile = CalibrationProfile(
                user_height_cm=data["user_height_cm"],
                scale_factor=data["scale_factor"],
                floor_offset_y=data["floor_offset_y"],
                shoulder_width=data["shoulder_width"],
                arm_length=data["arm_length"],
                leg_length=data["leg_length"],
                torso_length=data["torso_length"],
                hip_center=tuple(data["hip_center"]),
                captured_at=data.get("captured_at", 0),
            )
            logger.info("Calibration loaded from %s (scale=%.3f)", path, self._profile.scale_factor)
            return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.debug("No calibration loaded: %s", e)
            return False
