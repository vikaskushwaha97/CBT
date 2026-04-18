"""
models.py — Core data structures for Camera-Based Full Body Tracking.

Provides typed, immutable data containers used across every module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional


# ── MediaPipe 33-point landmark indices ─────────────────────────────────────
class LandmarkIndex(IntEnum):
    """MediaPipe Pose 33-point landmark indices."""
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


# ── VRChat OSC Tracker IDs ──────────────────────────────────────────────────
class TrackerID(Enum):
    """
    VRChat OSC tracker slot IDs.
    Slots 1-8 map to body parts; 'head' is a special alignment tracker.
    """
    HIP = 1
    CHEST = 2
    LEFT_FOOT = 3
    RIGHT_FOOT = 4
    LEFT_KNEE = 5
    RIGHT_KNEE = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    HEAD = "head"


# ── 3D Landmark ─────────────────────────────────────────────────────────────
@dataclass(slots=True)
class Landmark3D:
    """
    A single 3D body landmark in world coordinates (meters).

    Attributes
    ----------
    x : float   Horizontal (left-right), meters.
    y : float   Vertical (up-down), meters.
    z : float   Depth (towards/away from camera), meters.
    visibility : float   Confidence [0.0 – 1.0].
    """
    x: float
    y: float
    z: float
    visibility: float = 1.0


# ── VR Tracker Data ─────────────────────────────────────────────────────────
@dataclass(slots=True)
class TrackerData:
    """
    Position + rotation for a single VR tracker.

    Position: Unity world-space coordinates (meters), left-handed, +Y up.
    Rotation: Euler angles (degrees), applied in Z → X → Y order.
    """
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)


# ── Per-Person Result ────────────────────────────────────────────────────────
@dataclass
class PersonData:
    """
    Complete tracking result for a single detected person.
    """
    person_id: int
    landmarks: list[Landmark3D] = field(default_factory=list)
    trackers: dict[TrackerID, TrackerData] = field(default_factory=dict)
    confidence: float = 0.0  # average visibility across landmarks


# ── Frame-level Result ───────────────────────────────────────────────────────
@dataclass
class FrameResult:
    """
    Full processing result for a single camera frame.
    """
    timestamp: float = field(default_factory=time.time)
    persons: list[PersonData] = field(default_factory=list)
    fps: float = 0.0
    latency_ms: float = 0.0
    num_persons: int = 0
    osc_active: bool = False
    calibrated: bool = False

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for WebSocket transmission."""
        return {
            "timestamp": self.timestamp,
            "persons": [
                {
                    "id": p.person_id,
                    "confidence": round(p.confidence, 3),
                    "landmarks": [
                        {
                            "x": round(lm.x, 5),
                            "y": round(lm.y, 5),
                            "z": round(lm.z, 5),
                            "vis": round(lm.visibility, 3),
                        }
                        for lm in p.landmarks
                    ],
                    "trackers": {
                        t.name.lower(): {
                            "pos": [round(v, 5) for v in d.position],
                            "rot": [round(v, 3) for v in d.rotation],
                        }
                        for t, d in p.trackers.items()
                    },
                }
                for p in self.persons
            ],
            "fps": round(self.fps, 1),
            "latency_ms": round(self.latency_ms, 2),
            "num_persons": self.num_persons,
            "osc_active": self.osc_active,
            "calibrated": self.calibrated,
        }


# ── Calibration Profile ─────────────────────────────────────────────────────
@dataclass
class CalibrationProfile:
    """Stored calibration data from a T-pose capture."""
    user_height_cm: float = 177.8
    scale_factor: float = 1.0  # real_height / mediapipe_height
    floor_offset_y: float = 0.0
    shoulder_width: float = 0.0
    arm_length: float = 0.0
    leg_length: float = 0.0
    torso_length: float = 0.0
    hip_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    captured_at: float = 0.0
