"""Tests for One-Euro Filter and PoseFilter."""

import math
import pytest
from src.filters import OneEuroFilter, PoseFilter
from src.models import Landmark3D


class TestOneEuroFilter:
    def test_passthrough_first_sample(self):
        f = OneEuroFilter(freq=30)
        result = f(5.0, 0.0)
        assert result == 5.0

    def test_convergence_stationary(self):
        """Filter should converge to the stationary value."""
        f = OneEuroFilter(freq=30, min_cutoff=1.0, beta=0.0)
        # Feed constant value
        for i in range(100):
            val = f(10.0, i / 30.0)
        assert abs(val - 10.0) < 0.01

    def test_jitter_reduction(self):
        """High-frequency noise should be smoothed out."""
        f = OneEuroFilter(freq=30, min_cutoff=1.0, beta=0.001)
        results = []
        for i in range(100):
            # Signal = 5.0 + noise
            noise = 0.5 * math.sin(i * 2.0)  # high-freq noise
            val = f(5.0 + noise, i / 30.0)
            results.append(val)

        # Variance of filtered should be less than variance of raw noise
        filtered_var = sum((v - 5.0) ** 2 for v in results[-30:]) / 30
        assert filtered_var < 0.25  # noise variance was ~0.125

    def test_fast_movement_passes_through(self):
        """With high beta, fast movements should have low lag."""
        f = OneEuroFilter(freq=30, min_cutoff=1.0, beta=0.1)
        # Stationary then sudden jump
        for i in range(30):
            f(0.0, i / 30.0)
        # Jump to 10
        results = []
        for i in range(30, 60):
            val = f(10.0, i / 30.0)
            results.append(val)
        # Should be close to 10 within a few frames
        assert results[-1] > 9.5

    def test_reset(self):
        f = OneEuroFilter(freq=30)
        f(5.0, 0.0)
        f(6.0, 0.033)
        f.reset()
        # After reset, first sample should pass through
        assert f(100.0, 1.0) == 100.0


class TestPoseFilter:
    def test_filter_preserves_count(self):
        pf = PoseFilter(n_landmarks=33)
        landmarks = [Landmark3D(x=0.1*i, y=0.2*i, z=0.0, visibility=1.0) for i in range(33)]
        result = pf.filter(landmarks, 0.0)
        assert len(result) == 33

    def test_filter_preserves_visibility(self):
        pf = PoseFilter(n_landmarks=3)
        landmarks = [
            Landmark3D(x=1.0, y=2.0, z=3.0, visibility=0.95),
            Landmark3D(x=4.0, y=5.0, z=6.0, visibility=0.10),
            Landmark3D(x=7.0, y=8.0, z=9.0, visibility=0.50),
        ]
        result = pf.filter(landmarks, 0.0)
        assert result[0].visibility == 0.95
        assert result[1].visibility == 0.10
        assert result[2].visibility == 0.50

    def test_reset_clears_state(self):
        pf = PoseFilter(n_landmarks=3)
        lm = [Landmark3D(x=1.0, y=1.0, z=1.0, visibility=1.0)] * 3
        pf.filter(lm, 0.0)
        pf.filter(lm, 0.033)
        pf.reset()
        # After reset, should pass through
        result = pf.filter(lm, 1.0)
        assert result[0].x == 1.0
