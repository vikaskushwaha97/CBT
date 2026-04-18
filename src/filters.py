"""
filters.py — One-Euro Filter for real-time pose landmark jitter reduction.

The One-Euro filter is the standard adaptive low-pass filter for interactive
motion data.  It provides:
  • Heavy smoothing when the signal is stationary (removes jitter)
  • Light smoothing when the signal moves fast (reduces lag)

Reference: Casiez et al., "1€ Filter", CHI 2012.

Usage
-----
    pf = PoseFilter(n_landmarks=33, freq=30.0)
    smoothed = pf.filter(raw_landmarks, timestamp)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.models import Landmark3D


# ── Single-axis One-Euro Filter ─────────────────────────────────────────────
class OneEuroFilter:
    """
    Adaptive 1€ low-pass filter for a single scalar signal.

    Parameters
    ----------
    freq        : float  Expected signal frequency (Hz), e.g. 30 for 30 FPS.
    min_cutoff  : float  Minimum cutoff frequency.  Lower = smoother, more lag.
    beta        : float  Speed coefficient.  Higher = less lag on fast moves.
    d_cutoff    : float  Derivative cutoff frequency.
    """

    def __init__(
        self,
        freq: float = 30.0,
        min_cutoff: float = 1.7,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    @staticmethod
    def _alpha(cutoff: float, te: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x: float, t: float) -> float:
        if self._t_prev is None:
            # First sample — pass through
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            return x

        te = t - self._t_prev
        if te <= 0:
            te = 1.0 / self.freq  # fallback to nominal period

        # Derivative estimation
        dx = (x - self._x_prev) / te
        a_d = self._alpha(self.d_cutoff, te)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        # Adaptive cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)

        # Signal filtering
        a = self._alpha(cutoff, te)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat

    def reset(self):
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None


# ── Multi-Landmark Filter Bank ──────────────────────────────────────────────
class PoseFilter:
    """
    Wraps N×3 OneEuroFilter instances for a full pose (N landmarks × X/Y/Z).

    Each landmark's three coordinates get independent adaptive filtering.
    """

    def __init__(
        self,
        n_landmarks: int = 33,
        freq: float = 30.0,
        min_cutoff: float = 1.7,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self._n = n_landmarks
        self._params = dict(freq=freq, min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self._filters: list[tuple[OneEuroFilter, OneEuroFilter, OneEuroFilter]] = [
            (
                OneEuroFilter(**self._params),
                OneEuroFilter(**self._params),
                OneEuroFilter(**self._params),
            )
            for _ in range(n_landmarks)
        ]

    def filter(self, landmarks: list[Landmark3D], timestamp: float) -> list[Landmark3D]:
        """Apply per-axis One-Euro filtering to every landmark."""
        out: list[Landmark3D] = []
        for i, lm in enumerate(landmarks):
            if i >= self._n:
                break
            fx, fy, fz = self._filters[i]
            out.append(
                Landmark3D(
                    x=fx(lm.x, timestamp),
                    y=fy(lm.y, timestamp),
                    z=fz(lm.z, timestamp),
                    visibility=lm.visibility,
                )
            )
        return out

    def reset(self):
        for fx, fy, fz in self._filters:
            fx.reset()
            fy.reset()
            fz.reset()

    def update_params(self, min_cutoff: float | None = None, beta: float | None = None):
        """Live-update filter parameters (e.g. from dashboard slider)."""
        for fx, fy, fz in self._filters:
            for f in (fx, fy, fz):
                if min_cutoff is not None:
                    f.min_cutoff = min_cutoff
                if beta is not None:
                    f.beta = beta
