"""
config.py — Centralized configuration for Camera-Based Full Body Tracker.

Priority: CLI args > env vars > defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default, cast=str):
    val = os.environ.get(key, None)
    if val is None:
        return default
    try:
        if cast is bool:
            return val.lower() in ("1", "true", "yes")
        return cast(val)
    except (ValueError, TypeError):
        return default


@dataclass
class AppConfig:
    """
    Application configuration — all tuneable parameters in one place.
    """

    # ── Camera ──────────────────────────────────────────────────────────────
    camera_index: int = _env("FBT_CAMERA", 0, int)
    frame_width: int = _env("FBT_WIDTH", 640, int)
    frame_height: int = _env("FBT_HEIGHT", 480, int)
    target_fps: int = _env("FBT_FPS", 30, int)

    # ── Pose Detection ──────────────────────────────────────────────────────
    model_path: str = _env("FBT_MODEL", "pose_landmarker.task")
    min_detection_confidence: float = _env("FBT_DET_CONF", 0.6, float)
    min_tracking_confidence: float = _env("FBT_TRACK_CONF", 0.5, float)
    num_poses: int = _env("FBT_NUM_POSES", 5, int)
    visibility_threshold: float = _env("FBT_VIS_THRESH", 0.35, float)

    # ── Filtering (One-Euro) ────────────────────────────────────────────────
    filter_freq: float = _env("FBT_FILTER_FREQ", 30.0, float)
    filter_min_cutoff: float = _env("FBT_FILTER_MINCUTOFF", 1.7, float)
    filter_beta: float = _env("FBT_FILTER_BETA", 0.007, float)
    filter_d_cutoff: float = _env("FBT_FILTER_DCUTOFF", 1.0, float)

    # ── OSC Output ──────────────────────────────────────────────────────────
    osc_ip: str = _env("FBT_OSC_IP", "127.0.0.1")
    osc_port: int = _env("FBT_OSC_PORT", 9000, int)
    osc_enabled: bool = _env("FBT_OSC_ENABLED", False, bool)

    # ── Calibration ─────────────────────────────────────────────────────────
    user_height_cm: float = _env("FBT_HEIGHT_CM", 177.8, float)
    calibration_file: str = _env("FBT_CALIB_FILE", "calibration.json")

    # ── Tracker Selection ───────────────────────────────────────────────────
    send_hip: bool = True
    send_chest: bool = True
    send_feet: bool = True
    send_knees: bool = True
    send_elbows: bool = True
    send_head: bool = True

    # ── Server ──────────────────────────────────────────────────────────────
    server_host: str = _env("FBT_HOST", "0.0.0.0")
    server_port: int = _env("FBT_PORT", 8765, int)

    # ── IMU Sensors (ESP32 + MPU-6050 over WiFi UDP) ───────────────────────
    imu_enabled: bool = _env("FBT_IMU_ENABLED", False, bool)
    imu_port: int = _env("FBT_IMU_PORT", 6969, int)        # UDP listen port
    imu_sensor_count: int = _env("FBT_IMU_COUNT", 3, int)  # expected sensors
    imu_timeout_s: float = _env("FBT_IMU_TIMEOUT", 2.0, float)  # dead sensor threshold
    # Complementary filter: how much to trust IMU yaw vs camera yaw correction
    # 0.0 = full camera correction every frame, 1.0 = no correction (pure IMU)
    imu_yaw_alpha: float = _env("FBT_IMU_YAW_ALPHA", 0.97, float)
    # source_mode: "camera" | "imu" | "hybrid"
    source_mode: str = _env("FBT_SOURCE_MODE", "camera", str)

    # ── Paths (resolved at runtime) ─────────────────────────────────────────
    project_root: str = field(default="", init=False)

    def __post_init__(self):
        self.project_root = str(Path(__file__).parent.parent.resolve())
        # Resolve model path relative to project root
        if not os.path.isabs(self.model_path):
            self.model_path = os.path.join(self.project_root, self.model_path)

    @classmethod
    def from_args(cls, args) -> AppConfig:
        """Create config overriding defaults with argparse Namespace."""
        config = cls()
        if hasattr(args, "camera") and args.camera is not None:
            config.camera_index = args.camera
        if hasattr(args, "height") and args.height is not None:
            config.user_height_cm = args.height
        if hasattr(args, "osc_ip") and args.osc_ip is not None:
            config.osc_ip = args.osc_ip
        if hasattr(args, "osc_port") and args.osc_port is not None:
            config.osc_port = args.osc_port
        if hasattr(args, "no_osc") and args.no_osc:
            config.osc_enabled = False
        if hasattr(args, "osc") and args.osc:
            config.osc_enabled = True
        if hasattr(args, "poses") and args.poses is not None:
            config.num_poses = args.poses
        if hasattr(args, "port") and args.port is not None:
            config.server_port = args.port
        if hasattr(args, "imu") and args.imu:
            config.imu_enabled = True
            config.source_mode = "hybrid"
        if hasattr(args, "imu_port") and args.imu_port is not None:
            config.imu_port = args.imu_port
        if hasattr(args, "imu_count") and args.imu_count is not None:
            config.imu_sensor_count = args.imu_count
        return config

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        if self.frame_width < 320:
            errors.append("frame_width must be >= 320")
        if self.frame_height < 240:
            errors.append("frame_height must be >= 240")
        if not (0 < self.filter_min_cutoff <= 100):
            errors.append("filter_min_cutoff must be in (0, 100]")
        if self.filter_beta < 0:
            errors.append("filter_beta must be >= 0")
        if not (100 <= self.user_height_cm <= 250):
            errors.append("user_height_cm must be in [100, 250]")
        if self.num_poses < 1 or self.num_poses > 10:
            errors.append("num_poses must be in [1, 10]")
        if self.imu_enabled:
            if not (1024 <= self.imu_port <= 65535):
                errors.append("imu_port must be in [1024, 65535]")
            if not (0 < self.imu_sensor_count <= 8):
                errors.append("imu_sensor_count must be in [1, 8]")
            if self.source_mode not in ("camera", "imu", "hybrid"):
                errors.append("source_mode must be 'camera', 'imu', or 'hybrid'")
        return errors
