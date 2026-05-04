"""
skeleton.py — Landmark → VR Tracker solver.

Converts MediaPipe 3D world landmarks into VRChat-compatible tracker
positions and rotations (Unity left-handed coordinate system).

Coordinate transform
--------------------
MediaPipe world:  right-handed, Y down, origin at hip center
Unity / VRChat:   left-handed,  Y up,   1.0 = 1 meter

    unity_x =  mp_x   (lateral, already correct)
    unity_y = -mp_y   (flip vertical: MP Y-down → Unity Y-up)
    unity_z = -mp_z   (flip depth for left-handed)
"""

from __future__ import annotations

import math
from typing import Optional

from src.config import AppConfig
from src.models import (
    CalibrationProfile,
    Landmark3D,
    LandmarkIndex as LI,
    TrackerData,
    TrackerID,
)


class SkeletonSolver:
    """
    Converts 33 MediaPipe world landmarks into up to 8 VR tracker
    positions + rotations.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._calibration: Optional[CalibrationProfile] = None

    def set_calibration(self, profile: CalibrationProfile):
        self._calibration = profile

    def solve(self, landmarks: list[Landmark3D]) -> dict[TrackerID, TrackerData]:
        """
        Compute tracker positions and rotations from filtered landmarks.

        Returns dict mapping TrackerID → TrackerData.
        """
        if len(landmarks) < 33:
            return {}

        trackers: dict[TrackerID, TrackerData] = {}
        vis = self._config.visibility_threshold

        # ── Extract key landmarks ────────────────────────────────────────
        l_hip = landmarks[LI.LEFT_HIP]
        r_hip = landmarks[LI.RIGHT_HIP]
        l_shoulder = landmarks[LI.LEFT_SHOULDER]
        r_shoulder = landmarks[LI.RIGHT_SHOULDER]
        l_elbow = landmarks[LI.LEFT_ELBOW]
        r_elbow = landmarks[LI.RIGHT_ELBOW]
        l_knee = landmarks[LI.LEFT_KNEE]
        r_knee = landmarks[LI.RIGHT_KNEE]
        l_ankle = landmarks[LI.LEFT_ANKLE]
        r_ankle = landmarks[LI.RIGHT_ANKLE]
        nose = landmarks[LI.NOSE]
        l_ear = landmarks[LI.LEFT_EAR]
        r_ear = landmarks[LI.RIGHT_EAR]

        # ── Scale factor from calibration ────────────────────────────────
        scale = self._calibration.scale_factor if self._calibration else 1.0
        y_off = self._calibration.floor_offset_y if self._calibration else 0.0

        # ── Helper: convert to Unity coords with calibration ─────────────
        def to_unity(lm: Landmark3D) -> tuple[float, float, float]:
            return (
                lm.x * scale,
                -lm.y * scale + y_off,
                -lm.z * scale,
            )

        def midpoint(a: Landmark3D, b: Landmark3D) -> tuple[float, float, float]:
            ua, ub = to_unity(a), to_unity(b)
            return (
                (ua[0] + ub[0]) / 2,
                (ua[1] + ub[1]) / 2,
                (ua[2] + ub[2]) / 2,
            )

        def visible(*lms: Landmark3D) -> bool:
            return all(lm.visibility >= vis for lm in lms)

        # ── Hip (tracker 1) ──────────────────────────────────────────────
        if visible(l_hip, r_hip) and self._config.send_hip:
            pos = midpoint(l_hip, r_hip)
            rot = self._compute_segment_rotation(
                to_unity(r_hip), to_unity(l_hip), axis="lateral"
            )
            trackers[TrackerID.HIP] = TrackerData(position=pos, rotation=rot)

        # ── Chest (tracker 2) ────────────────────────────────────────────
        if visible(l_shoulder, r_shoulder) and self._config.send_chest:
            pos = midpoint(l_shoulder, r_shoulder)
            rot = self._compute_segment_rotation(
                to_unity(r_shoulder), to_unity(l_shoulder), axis="lateral"
            )
            trackers[TrackerID.CHEST] = TrackerData(position=pos, rotation=rot)

        # ── Feet (trackers 3, 4) ─────────────────────────────────────────
        if self._config.send_feet:
            if visible(l_ankle, l_knee):
                pos = to_unity(l_ankle)
                rot = self._compute_segment_rotation(
                    to_unity(l_knee), to_unity(l_ankle), axis="vertical"
                )
                trackers[TrackerID.LEFT_FOOT] = TrackerData(position=pos, rotation=rot)

            if visible(r_ankle, r_knee):
                pos = to_unity(r_ankle)
                rot = self._compute_segment_rotation(
                    to_unity(r_knee), to_unity(r_ankle), axis="vertical"
                )
                trackers[TrackerID.RIGHT_FOOT] = TrackerData(position=pos, rotation=rot)

        # ── Knees (trackers 5, 6) ────────────────────────────────────────
        if self._config.send_knees:
            if visible(l_knee, l_hip):
                pos = to_unity(l_knee)
                rot = self._compute_segment_rotation(
                    to_unity(l_hip), to_unity(l_knee), axis="vertical"
                )
                trackers[TrackerID.LEFT_KNEE] = TrackerData(position=pos, rotation=rot)

            if visible(r_knee, r_hip):
                pos = to_unity(r_knee)
                rot = self._compute_segment_rotation(
                    to_unity(r_hip), to_unity(r_knee), axis="vertical"
                )
                trackers[TrackerID.RIGHT_KNEE] = TrackerData(position=pos, rotation=rot)

        # ── Elbows (trackers 7, 8) ───────────────────────────────────────
        if self._config.send_elbows:
            if visible(l_elbow, l_shoulder):
                pos = to_unity(l_elbow)
                rot = self._compute_segment_rotation(
                    to_unity(l_shoulder), to_unity(l_elbow), axis="vertical"
                )
                trackers[TrackerID.LEFT_ELBOW] = TrackerData(position=pos, rotation=rot)

            if visible(r_elbow, r_shoulder):
                pos = to_unity(r_elbow)
                rot = self._compute_segment_rotation(
                    to_unity(r_shoulder), to_unity(r_elbow), axis="vertical"
                )
                trackers[TrackerID.RIGHT_ELBOW] = TrackerData(position=pos, rotation=rot)

        # ── Head (alignment tracker) ─────────────────────────────────────
        if self._config.send_head and visible(nose):
            if visible(l_ear, r_ear):
                pos = midpoint(l_ear, r_ear)
                # Blend with nose for better center
                np_ = to_unity(nose)
                pos = (
                    (pos[0] + np_[0]) / 2,
                    (pos[1] + np_[1]) / 2,
                    (pos[2] + np_[2]) / 2,
                )
                # Head yaw: direction from left ear to right ear
                ul_ear = to_unity(l_ear)
                ur_ear = to_unity(r_ear)
                dx = ur_ear[0] - ul_ear[0]
                dz = ur_ear[2] - ul_ear[2]
                head_yaw = math.degrees(math.atan2(dx, dz))
                rot = (0.0, head_yaw, 0.0)
            else:
                pos = to_unity(nose)
                rot = (0.0, 0.0, 0.0)
            trackers[TrackerID.HEAD] = TrackerData(position=pos, rotation=rot)

        return trackers

    @staticmethod
    def _compute_segment_rotation(
        parent: tuple[float, float, float],
        child: tuple[float, float, float],
        axis: str = "vertical",
    ) -> tuple[float, float, float]:
        """
        Compute Euler angles (degrees) for a bone segment.
        Applied in Z → X → Y order per VRChat spec.

        Now computes all three axes (pitch, yaw, roll) so that lateral
        body lean (roll) is captured from camera data.
        When IMU sensors are available, these camera estimates are replaced
        by the more accurate sensor quaternions in pipeline._apply_imu_rotations.
        """
        dx = child[0] - parent[0]
        dy = child[1] - parent[1]
        dz = child[2] - parent[2]

        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-6:
            return (0.0, 0.0, 0.0)

        # Pitch: elevation angle (X-axis rotation)
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, -dy / length))))
        # Yaw: horizontal direction (Y-axis rotation)
        yaw = math.degrees(math.atan2(dx, dz))
        # Roll: lateral lean, computed from the segment's own horizontal tilt
        # For vertical bones (legs, spine): roll = lean left/right
        # For lateral bones (shoulders, hips): roll = elevation difference
        if axis == "vertical":
            # Roll from how much the segment tilts left/right vs its vertical plane
            horiz = math.sqrt(dx * dx + dz * dz)
            roll = math.degrees(math.atan2(dx, max(horiz, 1e-6)) * 0.3)  # damped
        else:
            # Lateral segments: roll = elevation difference end-to-end
            roll = math.degrees(math.atan2(dy, max(abs(dx), 1e-6)))

        return (pitch, yaw, roll)
