"""Tests for skeleton solver coordinate transforms and tracker computation."""

import math
import pytest
from src.skeleton import SkeletonSolver
from src.config import AppConfig
from src.models import Landmark3D, TrackerID, LandmarkIndex as LI


def _make_landmarks(overrides=None):
    """Create a default set of 33 landmarks (all visible, at origin)."""
    lms = [Landmark3D(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    if overrides:
        for idx, vals in overrides.items():
            lms[idx] = Landmark3D(**vals)
    return lms


class TestSkeletonSolver:
    def setup_method(self):
        self.config = AppConfig()
        self.solver = SkeletonSolver(self.config)

    def test_empty_landmarks(self):
        result = self.solver.solve([])
        assert result == {}

    def test_hip_tracker_midpoint(self):
        """Hip should be midpoint of left/right hip."""
        lms = _make_landmarks({
            LI.LEFT_HIP: {"x": -0.1, "y": -0.5, "z": 0.0, "visibility": 1.0},
            LI.RIGHT_HIP: {"x": 0.1, "y": -0.5, "z": 0.0, "visibility": 1.0},
        })
        result = self.solver.solve(lms)
        assert TrackerID.HIP in result
        pos = result[TrackerID.HIP].position
        assert abs(pos[0] - 0.0) < 0.01  # midpoint X
        assert abs(pos[1] - 0.5) < 0.01  # flipped Y

    def test_chest_tracker(self):
        """Chest should be midpoint of shoulders."""
        lms = _make_landmarks({
            LI.LEFT_SHOULDER: {"x": -0.2, "y": -0.2, "z": 0.0, "visibility": 1.0},
            LI.RIGHT_SHOULDER: {"x": 0.2, "y": -0.2, "z": 0.0, "visibility": 1.0},
        })
        result = self.solver.solve(lms)
        assert TrackerID.CHEST in result

    def test_low_visibility_excluded(self):
        """Trackers should not be generated for low visibility landmarks."""
        lms = _make_landmarks({
            LI.LEFT_HIP: {"x": -0.1, "y": -0.5, "z": 0.0, "visibility": 0.1},
            LI.RIGHT_HIP: {"x": 0.1, "y": -0.5, "z": 0.0, "visibility": 0.1},
        })
        result = self.solver.solve(lms)
        assert TrackerID.HIP not in result

    def test_coordinate_flip(self):
        """Unity coords: Y should be flipped, Z should be flipped."""
        lms = _make_landmarks({
            LI.LEFT_ANKLE: {"x": 0.1, "y": -1.0, "z": 0.5, "visibility": 1.0},
            LI.LEFT_KNEE: {"x": 0.1, "y": -0.5, "z": 0.3, "visibility": 1.0},
        })
        result = self.solver.solve(lms)
        assert TrackerID.LEFT_FOOT in result
        pos = result[TrackerID.LEFT_FOOT].position
        assert pos[0] == pytest.approx(0.1, abs=0.01)   # x unchanged
        assert pos[1] == pytest.approx(1.0, abs=0.01)    # y flipped
        assert pos[2] == pytest.approx(-0.5, abs=0.01)   # z flipped

    def test_rotation_format(self):
        """Rotation should be (pitch, yaw, roll) tuple of 3 floats."""
        lms = _make_landmarks({
            LI.LEFT_HIP: {"x": -0.1, "y": -0.5, "z": 0.0, "visibility": 1.0},
            LI.RIGHT_HIP: {"x": 0.1, "y": -0.5, "z": 0.0, "visibility": 1.0},
        })
        result = self.solver.solve(lms)
        rot = result[TrackerID.HIP].rotation
        assert len(rot) == 3
        assert all(isinstance(v, float) for v in rot)
