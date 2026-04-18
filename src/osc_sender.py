"""
osc_sender.py — OSC UDP transmitter for VRChat full-body tracking.

Sends tracker position/rotation data per the VRChat OSC Trackers spec:
    /tracking/trackers/{id}/position   [float, float, float]
    /tracking/trackers/{id}/rotation   [float, float, float]

Where id = 1–8 for body trackers, "head" for alignment.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import AppConfig
from src.models import TrackerData, TrackerID

logger = logging.getLogger(__name__)

# Lazy import — only loaded if OSC is enabled
_osc_client = None


def _get_client(ip: str, port: int):
    global _osc_client
    if _osc_client is None:
        try:
            from pythonosc.udp_client import SimpleUDPClient
            _osc_client = SimpleUDPClient(ip, port)
            logger.info("OSC client connected → %s:%d", ip, port)
        except ImportError:
            logger.error(
                "python-osc not installed. Run: pip install python-osc"
            )
            return None
    return _osc_client


class OSCSender:
    """
    Sends VRChat-compatible OSC tracker data over UDP.

    Usage
    -----
        sender = OSCSender(config)
        sender.send_tracker(TrackerID.HIP, tracker_data)
        sender.send_all(trackers_dict)
    """

    def __init__(self, config: AppConfig):
        self._ip = config.osc_ip
        self._port = config.osc_port
        self._client = None
        self._enabled = config.osc_enabled
        self._packets_sent = 0

    @property
    def is_active(self) -> bool:
        return self._enabled and self._client is not None

    @property
    def packets_sent(self) -> int:
        return self._packets_sent

    def enable(self, ip: Optional[str] = None, port: Optional[int] = None):
        if ip:
            self._ip = ip
        if port:
            self._port = port
        self._client = _get_client(self._ip, self._port)
        self._enabled = self._client is not None
        return self._enabled

    def disable(self):
        self._enabled = False
        logger.info("OSC output disabled")

    def send_tracker(self, tracker_id: TrackerID, data: TrackerData) -> None:
        """Send position + rotation for a single tracker."""
        if not self._enabled:
            return
        if self._client is None:
            self._client = _get_client(self._ip, self._port)
            if self._client is None:
                return

        tid = tracker_id.value  # int (1-8) or str ("head")
        try:
            self._client.send_message(
                f"/tracking/trackers/{tid}/position",
                list(data.position),
            )
            self._client.send_message(
                f"/tracking/trackers/{tid}/rotation",
                list(data.rotation),
            )
            self._packets_sent += 2
        except Exception as e:
            logger.warning("OSC send failed: %s", e)

    def send_all(self, trackers: dict[TrackerID, TrackerData]) -> None:
        """Send all tracker data in one batch."""
        for tid, data in trackers.items():
            self.send_tracker(tid, data)
