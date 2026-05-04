"""
imu_source.py — UDP receiver for ESP32 + MPU-6050 sensor nodes.

Architecture
------------
IMUSource runs a background daemon thread that listens on a UDP socket.
Each incoming packet is parsed from the 48-byte binary format, validated,
and stored in a per-sensor SensorState dictionary.

The pipeline calls imu_source.get_all_states() each frame to retrieve
the latest quaternion for every active sensor, then overrides the
camera-estimated rotation in TrackerData with the (more accurate) IMU value.

Yaw Drift Correction
---------------------
MPU-6050 has no magnetometer, so yaw drifts ~1-5°/minute.
The pipeline calls apply_yaw_correction(sensor_id, camera_yaw_deg) each frame,
which feeds the camera's yaw estimate into a complementary filter:

    imu_yaw_corrected = alpha * imu_yaw + (1 - alpha) * camera_yaw

alpha = config.imu_yaw_alpha (default 0.97): 97% trust in IMU each frame,
3% correction from camera. This eliminates drift over ~30 seconds.

UDP Packet Format (48 bytes, little-endian)
-------------------------------------------
  Offset  Type    Field
  0       uint8   magic_h  (0xCA)
  1       uint8   magic_l  (0xFE)
  2       uint8   sensor_id (0-7, maps to SensorID enum)
  3       uint8   ptype     (0x01 = quaternion+raw)
  4-7     float32 qw
  8-11    float32 qx
  12-15   float32 qy
  16-19   float32 qz
  20-23   float32 ax  (linear accel, g)
  24-27   float32 ay
  28-31   float32 az
  32-35   float32 gx  (gyro, deg/s)
  36-39   float32 gy
  40-43   float32 gz
  44-47   uint32  ts_ms (ESP32 millis())
"""

from __future__ import annotations

import logging
import select
import socket
import struct
import threading
import time
from typing import Optional

from src.config import AppConfig
from src.models import IMUReading, SensorID, SensorState

logger = logging.getLogger(__name__)

# ── Wire protocol constants ───────────────────────────────────────────────────
_MAGIC_H   = 0xCA
_MAGIC_L   = 0xFE
_PTYPE_IMU = 0x01
_FMT       = "<BBBBffffffffffI"   # 48 bytes, little-endian
_PKT_SIZE  = struct.calcsize(_FMT)  # must be 48


class IMUSource:
    """
    Background UDP receiver for ESP32 + MPU-6050 sensor nodes.

    Usage
    -----
        imu = IMUSource(config)
        imu.start()
        ...
        states = imu.get_all_states()
        imu.apply_yaw_correction(SensorID.HIP, camera_hip_yaw_deg)
        ...
        imu.stop()
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._port   = config.imu_port
        self._alpha  = config.imu_yaw_alpha   # complementary filter weight

        # Per-sensor state, keyed by raw sensor_id int
        self._states: dict[int, SensorState] = {}
        self._lock   = threading.Lock()

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Statistics
        self._total_packets = 0
        self._bad_packets   = 0

        logger.info("IMUSource created (port=%d, yaw_alpha=%.3f)", self._port, self._alpha)

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> bool:
        """Open UDP socket and start listener thread. Returns True on success."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", self._port))
            self._sock.setblocking(False)
            self._running = True
            self._thread = threading.Thread(
                target=self._recv_loop, daemon=True, name="imu-recv"
            )
            self._thread.start()
            logger.info("IMUSource listening on UDP :%d", self._port)
            return True
        except OSError as e:
            logger.error("IMUSource failed to bind port %d: %s", self._port, e)
            return False

    def stop(self):
        """Signal receiver thread to stop and close socket."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info(
            "IMUSource stopped. Packets: total=%d bad=%d",
            self._total_packets, self._bad_packets,
        )

    @property
    def is_running(self) -> bool:
        return self._running and (self._thread is not None) and self._thread.is_alive()

    # ── State access ──────────────────────────────────────────────────────────
    def get_state(self, sensor_id: int) -> Optional[SensorState]:
        """Return latest state for a specific sensor, or None if never seen."""
        with self._lock:
            return self._states.get(sensor_id)

    def get_all_states(self) -> list[SensorState]:
        """Return states for all known sensors, marking stale ones disconnected."""
        now = time.time()
        timeout = self._config.imu_timeout_s
        with self._lock:
            for state in self._states.values():
                stale = (now - state.last_packet_at) > timeout
                if stale and state.is_connected:
                    state.is_connected = False
                    logger.warning("Sensor %d timed out", state.sensor_id)
            return list(self._states.values())

    def get_latest_reading(self, sensor_id: int) -> Optional[IMUReading]:
        """Convenience: return just the last IMUReading for a sensor."""
        with self._lock:
            state = self._states.get(sensor_id)
            return state.last_reading if state else None

    def connected_count(self) -> int:
        """Number of sensors currently sending data."""
        with self._lock:
            return sum(1 for s in self._states.values() if s.is_connected)

    # ── Yaw drift correction ──────────────────────────────────────────────────
    def apply_yaw_correction(self, sensor_id: int, camera_yaw_deg: float):
        """
        Feed camera-estimated yaw into the complementary filter for this sensor.

        Call once per frame from the pipeline after camera skeleton is solved.
        The corrected yaw is applied during the next get_corrected_rotation() call.

        Parameters
        ----------
        sensor_id      : SensorID int value
        camera_yaw_deg : Yaw estimated from MediaPipe landmarks (degrees)
        """
        with self._lock:
            state = self._states.get(sensor_id)
            if state is None or state.last_reading is None:
                return
            # Extract current IMU yaw
            _, imu_yaw, _ = state.last_reading.to_euler_deg()
            # Complementary blend
            corrected = self._alpha * imu_yaw + (1.0 - self._alpha) * camera_yaw_deg
            state.yaw_correction_deg = corrected - imu_yaw  # store as offset

    def get_corrected_rotation(self, sensor_id: int) -> Optional[tuple[float, float, float]]:
        """
        Return (pitch, yaw, roll) in degrees with yaw-drift correction applied.

        Returns None if sensor has no data.
        """
        with self._lock:
            state = self._states.get(sensor_id)
            if state is None or state.last_reading is None:
                return None
            pitch, yaw, roll = state.last_reading.to_euler_deg()
            yaw_corrected = yaw + state.yaw_correction_deg
            return (pitch, yaw_corrected, roll)

    # ── Background receiver thread ────────────────────────────────────────────
    def _recv_loop(self):
        logger.debug("IMU receiver thread started")
        while self._running:
            try:
                # Non-blocking poll with 100ms timeout
                ready, _, _ = select.select([self._sock], [], [], 0.1)
                if not ready:
                    continue
                data, addr = self._sock.recvfrom(256)
                self._handle_packet(data, addr)
            except OSError:
                break  # socket closed
            except Exception as e:
                logger.debug("IMU recv error: %s", e)
        logger.debug("IMU receiver thread exited")

    def _handle_packet(self, data: bytes, addr):
        """Parse one UDP packet and update sensor state."""
        if len(data) != _PKT_SIZE:
            self._bad_packets += 1
            return

        try:
            (magic_h, magic_l, sensor_id, ptype,
             qw, qx, qy, qz,
             ax, ay, az,
             gx, gy, gz,
             ts_ms) = struct.unpack(_FMT, data)
        except struct.error:
            self._bad_packets += 1
            return

        # Validate magic bytes and packet type
        if magic_h != _MAGIC_H or magic_l != _MAGIC_L or ptype != _PTYPE_IMU:
            self._bad_packets += 1
            return

        if sensor_id > 7:
            self._bad_packets += 1
            return

        reading = IMUReading(
            sensor_id=sensor_id,
            qw=qw, qx=qx, qy=qy, qz=qz,
            ax=ax, ay=ay, az=az,
            gx=gx, gy=gy, gz=gz,
            sensor_timestamp_ms=ts_ms,
        )

        now = time.time()
        with self._lock:
            if sensor_id not in self._states:
                self._states[sensor_id] = SensorState(sensor_id=sensor_id)
                logger.info("New IMU sensor connected: id=%d from %s", sensor_id, addr[0])

            state = self._states[sensor_id]
            was_connected = state.is_connected
            state.is_connected  = True
            state.last_packet_at = now
            state.packet_count  += 1
            state.last_reading  = reading

            if not was_connected:
                logger.info("Sensor %d reconnected (%d total packets)", sensor_id, state.packet_count)

        self._total_packets += 1
