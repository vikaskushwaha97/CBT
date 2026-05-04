"""
models.py — Core data structures for Camera-Based Full Body Tracking.

Provides typed, immutable data containers used across every module.
Extended with IMU sensor data types for ESP32 + MPU-6050 hybrid tracking.
"""

from __future__ import annotations

import math
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
    imu_active: bool = False                                # True when IMU sensors contributing
    sensor_states: list[SensorState] = field(default_factory=list)

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
            "imu_active": self.imu_active,
            "sensors": [
                {
                    "id": s.sensor_id,
                    "connected": s.is_connected,
                    "latency_ms": round(s.latency_ms, 1),
                    "packets": s.packet_count,
                    "signal_ok": s.signal_ok,
                }
                for s in self.sensor_states
            ],
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


# ── IMU Sensor Types (ESP32 + MPU-6050) ──────────────────────────────────────
class SensorID(IntEnum):
    """
    Physical body placement of each IMU sensor node.
    Minimum viable: HIP (0) + LEFT_ANKLE (4) + RIGHT_ANKLE (5).
    """
    HIP          = 0   # Pelvis center  — most critical tracker
    CHEST        = 1   # Upper torso
    LEFT_THIGH   = 2   # Left thigh (drives LEFT_KNEE tracker)
    RIGHT_THIGH  = 3   # Right thigh (drives RIGHT_KNEE tracker)
    LEFT_ANKLE   = 4   # Left foot orientation
    RIGHT_ANKLE  = 5   # Right foot orientation
    LEFT_WRIST   = 6   # Left wrist (drives LEFT_ELBOW tracker)
    RIGHT_WRIST  = 7   # Right wrist (drives RIGHT_ELBOW tracker)


# Maps sensor body placement → VR tracker slot
SENSOR_TO_TRACKER: dict[SensorID, TrackerID] = {
    SensorID.HIP:          TrackerID.HIP,
    SensorID.CHEST:        TrackerID.CHEST,
    SensorID.LEFT_THIGH:   TrackerID.LEFT_KNEE,
    SensorID.RIGHT_THIGH:  TrackerID.RIGHT_KNEE,
    SensorID.LEFT_ANKLE:   TrackerID.LEFT_FOOT,
    SensorID.RIGHT_ANKLE:  TrackerID.RIGHT_FOOT,
    SensorID.LEFT_WRIST:   TrackerID.LEFT_ELBOW,
    SensorID.RIGHT_WRIST:  TrackerID.RIGHT_ELBOW,
}


@dataclass(slots=True)
class IMUReading:
    """
    One UDP packet from an ESP32 + MPU-6050 node running DMP mode.

    Binary wire format (48 bytes, little-endian):
        magic_h  : uint8   0xCA
        magic_l  : uint8   0xFE
        sensor_id: uint8   SensorID (0-7)
        ptype    : uint8   0x01 = quaternion+raw packet
        qw,qx,qy,qz: float32 × 4  — DMP quaternion
        ax,ay,az    : float32 × 3  — linear accel (g)
        gx,gy,gz    : float32 × 3  — gyro (deg/s)
        ts_ms    : uint32  — ESP32 millis()
    """
    sensor_id: int                          # SensorID value (0-7)
    qw: float = 1.0                         # DMP quaternion w
    qx: float = 0.0                         # DMP quaternion x
    qy: float = 0.0                         # DMP quaternion y
    qz: float = 0.0                         # DMP quaternion z
    ax: float = 0.0                         # Linear accel X (g)
    ay: float = 0.0                         # Linear accel Y (g)
    az: float = 0.0                         # Linear accel Z (g)
    gx: float = 0.0                         # Gyro X (deg/s)
    gy: float = 0.0                         # Gyro Y (deg/s)
    gz: float = 0.0                         # Gyro Z (deg/s)
    sensor_timestamp_ms: int = 0            # ESP32 millis()
    received_at: float = field(default_factory=time.time)

    def to_euler_deg(self) -> tuple[float, float, float]:
        """Convert DMP quaternion → (pitch, yaw, roll) in degrees."""
        w, x, y, z = self.qw, self.qx, self.qy, self.qz
        # Roll (rotation around X)
        sinr = 2.0 * (w * x + y * z)
        cosr = 1.0 - 2.0 * (x * x + y * y)
        roll = math.degrees(math.atan2(sinr, cosr))
        # Pitch (rotation around Y)
        sinp = 2.0 * (w * y - z * x)
        sinp = max(-1.0, min(1.0, sinp))
        pitch = math.degrees(math.asin(sinp))
        # Yaw (rotation around Z) — drifts without magnetometer
        siny = 2.0 * (w * z + x * y)
        cosy = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.degrees(math.atan2(siny, cosy))
        return (pitch, yaw, roll)


@dataclass
class SensorState:
    """Live connection + signal health of one IMU sensor node."""
    sensor_id: int
    is_connected: bool = False
    last_packet_at: float = 0.0
    packet_count: int = 0
    last_reading: Optional[IMUReading] = None
    yaw_correction_deg: float = 0.0         # Camera-provided yaw offset

    @property
    def latency_ms(self) -> float:
        if self.last_packet_at == 0.0:
            return 9999.0
        return (time.time() - self.last_packet_at) * 1000.0

    @property
    def signal_ok(self) -> bool:
        return self.is_connected and self.latency_ms < 500.0
