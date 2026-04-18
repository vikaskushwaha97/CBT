"""
src — Camera-Based Full Body Tracking System.

Public API exports for convenience.
"""

from src.config import AppConfig
from src.models import (
    CalibrationProfile,
    FrameResult,
    Landmark3D,
    LandmarkIndex,
    PersonData,
    TrackerData,
    TrackerID,
)

__version__ = "1.0.0"
__all__ = [
    "AppConfig",
    "CalibrationProfile",
    "FrameResult",
    "Landmark3D",
    "LandmarkIndex",
    "PersonData",
    "TrackerData",
    "TrackerID",
]
