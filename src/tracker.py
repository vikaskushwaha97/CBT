"""
tracker.py — Pose detection + all avatar rendering for Dance Avatar.

Public API
----------
PoseTracker           — wraps MediaPipe (Tasks API or legacy, auto-selected)
SmoothingBuffer       — per-landmark EMA jitter reduction
draw_cartoon_avatar   — NEW: cartoon-style head/body/arms/legs avatar
draw_stick_figure     — original neon stick figure (kept for compatibility)
"""

import os
import cv2
import numpy as np
import math


# ──────────────────────────────────────────────────────────────────────────────
# MediaPipe backend — Tasks API if .task model file is present, else legacy
# ──────────────────────────────────────────────────────────────────────────────
_TASK_FILE = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task")
_USE_TASKS = os.path.exists(_TASK_FILE)

if _USE_TASKS:
    from mediapipe.tasks.python import vision as _vis
    from mediapipe.tasks.python.core import base_options as _bo
    from mediapipe import Image as _Img, ImageFormat as _ImgFmt

    class PoseTracker:
        def __init__(self, **_):
            opts = _vis.PoseLandmarkerOptions(
                base_options=_bo.BaseOptions(
                    model_asset_path=os.path.abspath(_TASK_FILE)),
                num_poses=5,
                running_mode=_vis.RunningMode.IMAGE,
            )
            self._det = _vis.PoseLandmarker.create_from_options(opts)

        def process(self, frame_bgr: np.ndarray):
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self._det.detect(_Img(image_format=_ImgFmt.SRGB, data=rgb))
            return res.pose_landmark[0] if res.pose_landmarks else None

        def close(self):
            self._det.close()

else:
    import mediapipe as mp
    _mp_pose = mp.solutions.pose

    class _Shim:
        """Landmark shim — makes Tasks-API and legacy landmarks look identical."""
        __slots__ = ("x", "y", "visibility")
        def __init__(self, x, y, v): self.x, self.y, self.visibility = x, y, v

    class PoseTracker:
        def __init__(self, min_detection_confidence=0.6,
                     min_tracking_confidence=0.5):
            self._pose = _mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                smooth_landmarks=True,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )

        def process(self, frame_bgr: np.ndarray):
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = self._pose.process(rgb)
            rgb.flags.writeable = True
            if res.pose_landmarks is None:
                return None
            return [_Shim(lm.x, lm.y, lm.visibility)
                    for lm in res.pose_landmarks.landmark]

        def close(self):
            self._pose.close()


# ──────────────────────────────────────────────────────────────────────────────
# Smoothing
# ──────────────────────────────────────────────────────────────────────────────
class SmoothingBuffer:
    """
    Per-landmark exponential moving average (EMA) for jitter reduction.

    Parameters
    ----------
    n_landmarks : int   Number of landmarks (33 for MediaPipe full-body)
    alpha       : float Blend factor 0 < alpha <= 1.
                        1.0 = no smoothing; 0.15 = light smoothing.
                        0.15 is ideal for crisp, responsive real-time tracking.
    """

    def __init__(self, n_landmarks: int = 33, alpha: float = 0.15):
        self._alpha = alpha
        self._prev  = [None] * n_landmarks   # stored as (x, y) tuples

    def update(self, landmarks) -> list:
        """
        Accept raw landmark list; return new list of smoothed shim objects.
        Visibility values are passed through unchanged.
        """
        out = []
        for i, lm in enumerate(landmarks):
            raw = (lm.x, lm.y)
            if self._prev[i] is None:
                self._prev[i] = raw
            else:
                px, py = self._prev[i]
                sx = self._alpha * raw[0] + (1 - self._alpha) * px
                sy = self._alpha * raw[1] + (1 - self._alpha) * py
                self._prev[i] = (sx, sy)

            class _S:
                pass
            s = _S()
            s.x, s.y, s.visibility = self._prev[i][0], self._prev[i][1], lm.visibility
            out.append(s)
        return out

    def reset(self):
        self._prev = [None] * len(self._prev)


# ──────────────────────────────────────────────────────────────────────────────
# Internal drawing helpers (shared by both renderers)
# ──────────────────────────────────────────────────────────────────────────────
def _px(lm, w: int, h: int) -> tuple:
    return int(lm.x * w), int(lm.y * h)

def _ok(lm, thresh: float = 0.35) -> bool:
    return lm.visibility >= thresh

def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

def _angle(p1, p2) -> float:
    """Degrees from horizontal for vector p1 → p2."""
    return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))


# ──────────────────────────────────────────────────────────────────────────────
# Cartoon avatar — colour palette
# ──────────────────────────────────────────────────────────────────────────────
_SKIN    = (190, 215, 255)   # warm skin on dark canvas  (BGR)
_SHIRT   = ( 50, 130, 255)   # torso + upper arm
_PANTS   = ( 25,  65, 175)   # lower body + thigh
_SHOE    = ( 15,  15,  70)   # foot stub
_HAIR    = ( 25,  15,  70)   # dark navy hair
_OUTLINE = (255, 255, 255)   # crisp white outline
_EYE_BG  = (230, 230, 230)
_IRIS    = ( 70,  45, 195)
_PUPIL   = (  0,   0,   0)
_SHINE   = (255, 255, 255)
_MOUTH   = ( 75,  55, 120)


# ── Sub-renderers ─────────────────────────────────────────────────────────────
def _limb(img, p1, p2, fill_color, thickness: int):
    """Rounded limb: white outline + filled centre + capped ends."""
    t = max(3, thickness)
    cv2.line(img, p1, p2, _OUTLINE, t + 3, cv2.LINE_AA)
    cv2.circle(img, p1, (t + 3) // 2, _OUTLINE, -1, cv2.LINE_AA)
    cv2.circle(img, p2, (t + 3) // 2, _OUTLINE, -1, cv2.LINE_AA)
    cv2.line(img, p1, p2, fill_color, t, cv2.LINE_AA)
    cv2.circle(img, p1, t // 2, fill_color, -1, cv2.LINE_AA)
    cv2.circle(img, p2, t // 2, fill_color, -1, cv2.LINE_AA)


def _torso_rect(img, shoulder_mid, hip_mid, width: int):
    """Filled rotated rectangle from shoulder mid-point to hip mid-point."""
    angle = _angle(shoulder_mid, hip_mid)
    cx = int((shoulder_mid[0] + hip_mid[0]) / 2)
    cy = int((shoulder_mid[1] + hip_mid[1]) / 2)
    length = max(20, int(_dist(shoulder_mid, hip_mid)))
    rect   = ((cx, cy), (width, length), angle + 90)
    box    = cv2.boxPoints(rect).astype(np.int32)
    cv2.drawContours(img, [box], 0, _OUTLINE,  3, cv2.LINE_AA)
    cv2.fillPoly(img, [box], _SHIRT)


def _head(img, cx: int, cy: int, r: int):
    """Chibi anime head: hair blob, round face, big eyes, mouth."""
    # Hair (behind face)
    for a_deg in range(0, 360, 15):
        a  = math.radians(a_deg)
        hx = int(cx + (r + 5) * math.cos(a))
        hy = int(cy - int(r * 0.25) + (r + 3) * math.sin(a))
        cv2.circle(img, (hx, hy), 8, _HAIR, -1, cv2.LINE_AA)

    # Face circle
    cv2.circle(img, (cx, cy), r + 2, _OUTLINE, 3, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r,     _SKIN,    -1, cv2.LINE_AA)

    # Eyes — placed just above centre
    ey     = cy - int(r * 0.05)
    ex_off = int(r * 0.32)
    er_x   = max(3, int(r * 0.20))
    er_y   = max(4, int(r * 0.26))

    for sign in (-1, 1):
        ex = cx + sign * ex_off
        cv2.ellipse(img, (ex, ey), (er_x, er_y),     0, 0, 360, _EYE_BG, -1, cv2.LINE_AA)
        cv2.ellipse(img, (ex, ey), (int(er_x * 0.65), int(er_y * 0.70)),
                    0, 0, 360, _IRIS, -1, cv2.LINE_AA)
        cv2.circle(img, (ex, ey), max(2, int(er_x * 0.30)), _PUPIL, -1, cv2.LINE_AA)
        sx = ex - int(er_x * 0.20)
        sy = ey - int(er_y * 0.28)
        cv2.circle(img, (sx, sy), max(1, int(er_x * 0.14)), _SHINE, -1, cv2.LINE_AA)
        # Top lash
        cv2.ellipse(img, (ex, ey), (er_x + 1, er_y + 1),
                    0, 195, 345, (20, 10, 10), 2, cv2.LINE_AA)

    # Mouth
    my = cy + int(r * 0.40)
    cv2.ellipse(img, (cx, my), (int(r * 0.18), int(r * 0.10)),
                0, 0, 180, _MOUTH, 2, cv2.LINE_AA)


# ── Main function ──────────────────────────────────────────────────────────────
def draw_cartoon_avatar(canvas: np.ndarray, landmarks) -> None:
    """
    Draw a proportional cartoon avatar onto *canvas* (dark BGR, in-place).

    MediaPipe landmark indices used:
      0  nose
      7  left_ear       8  right_ear
      11 left_shoulder  12 right_shoulder
      13 left_elbow     14 right_elbow
      15 left_wrist     16 right_wrist
      23 left_hip       24 right_hip
      25 left_knee      26 right_knee
      27 left_ankle     28 right_ankle
    """
    h, w = canvas.shape[:2]

    # ── collect landmark pixel coords (None if not visible) ──────────────
    def get(idx, thresh=0.35):
        lm = landmarks[idx]
        return _px(lm, w, h) if _ok(lm, thresh) else None

    ls, rs = get(11), get(12)   # shoulders
    le, re = get(13), get(14)   # elbows
    lw, rw = get(15), get(16)   # wrists
    lh, rh = get(23), get(24)   # hips
    lk, rk = get(25), get(26)   # knees
    la, ra = get(27), get(28)   # ankles
    nose   = get(0,  0.30)
    el     = get(7,  0.20)       # left ear
    er     = get(8,  0.20)       # right ear

    # ── composite mid-points ─────────────────────────────────────────────
    shoulder_mid = (((ls[0]+rs[0])//2, (ls[1]+rs[1])//2)
                    if ls and rs else None)
    hip_mid      = (((lh[0]+rh[0])//2, (lh[1]+rh[1])//2)
                    if lh and rh else None)

    # ── proportional sizing based on shoulder width ──────────────────────
    sw = max(30.0, _dist(ls, rs) if ls and rs else 80.0)

    arm_thick  = max(8,  int(sw * 0.14))
    leg_thick  = max(10, int(sw * 0.18))
    body_w     = max(20, int(sw * 0.55))

    # ── draw back-to-front ───────────────────────────────────────────────

    # RIGHT leg (slightly behind left visually)
    if rh and rk:
        _limb(canvas, rh, rk, _PANTS, leg_thick)
    if rk and ra:
        _limb(canvas, rk, ra, _PANTS, max(6, leg_thick - 2))
        # foot stub
        fd = _angle(rk, ra)
        fx = int(ra[0] + 13 * math.cos(math.radians(fd + 70)))
        fy = int(ra[1] + 13 * math.sin(math.radians(fd + 70)))
        _limb(canvas, ra, (fx, fy), _SHOE, max(5, leg_thick - 3))

    # LEFT leg
    if lh and lk:
        _limb(canvas, lh, lk, _PANTS, leg_thick)
    if lk and la:
        _limb(canvas, lk, la, _PANTS, max(6, leg_thick - 2))
        fd = _angle(lk, la)
        fx = int(la[0] + 13 * math.cos(math.radians(fd + 70)))
        fy = int(la[1] + 13 * math.sin(math.radians(fd + 70)))
        _limb(canvas, la, (fx, fy), _SHOE, max(5, leg_thick - 3))

    # TORSO
    if shoulder_mid and hip_mid:
        _torso_rect(canvas, shoulder_mid, hip_mid, body_w)

    # RIGHT arm (back-ish)
    if rs and re:
        _limb(canvas, rs, re, _SHIRT, arm_thick)
    if re and rw:
        _limb(canvas, re, rw, _SKIN,  max(5, arm_thick - 2))

    # LEFT arm (front)
    if ls and le:
        _limb(canvas, ls, le, _SHIRT, arm_thick)
    if le and lw:
        _limb(canvas, le, lw, _SKIN,  max(5, arm_thick - 2))

    # Hands
    for pt in (lw, rw):
        if pt:
            cv2.circle(canvas, pt, max(4, arm_thick // 2),
                       _OUTLINE, 2, cv2.LINE_AA)
            cv2.circle(canvas, pt, max(3, arm_thick // 2 - 1),
                       _SKIN,   -1, cv2.LINE_AA)

    # HEAD
    if nose or (el and er):
        if el and er:
            hcx = int((el[0] + er[0]) / 2)
            hcy = int((el[1] + er[1]) / 2)
            if nose:
                hcx = int((hcx + nose[0]) / 2)
                hcy = int((hcy + nose[1]) / 2)
            head_r = max(18, int(_dist(el, er) * 0.85))
        else:
            hcx, hcy = nose
            head_r = max(18, int(sw * 0.30))
        _head(canvas, hcx, hcy, head_r)


# ──────────────────────────────────────────────────────────────────────────────
# Original neon stick figure (kept; used by "stick" mode in main.py)
# ──────────────────────────────────────────────────────────────────────────────
_STICK_CONN = [
    (11,12),(11,23),(12,24),(23,24),
    (11,13),(13,15),(12,14),(14,16),
    (23,25),(25,27),(24,26),(26,28),(7,8),
]
_L = {7,11,13,15,23,25,27}
_R = {8,12,14,16,24,26,28}

def _sc(a, b):
    if a in _L or b in _L: return (200, 60, 255)
    if a in _R or b in _R: return (255, 210, 30)
    return (60, 255, 140)

def draw_stick_figure(canvas: np.ndarray, landmarks) -> None:
    h, w = canvas.shape[:2]
    for ai, bi in _STICK_CONN:
        la, lb = landmarks[ai], landmarks[bi]
        if not _ok(la) or not _ok(lb): continue
        p1, p2 = _px(la, w, h), _px(lb, w, h)
        c = _sc(ai, bi)
        cv2.line(canvas, p1, p2, tuple(v//5 for v in c), 20, cv2.LINE_AA)
        cv2.line(canvas, p1, p2, tuple(v//2 for v in c),  8, cv2.LINE_AA)
        cv2.line(canvas, p1, p2, c, 2, cv2.LINE_AA)
    for idx in [11,12,13,14,15,16,23,24,25,26,27,28]:
        lm = landmarks[idx]
        if not _ok(lm): continue
        pt = _px(lm, w, h)
        c  = _sc(idx, idx)
        cv2.circle(canvas, pt, 9, tuple(v//4 for v in c), -1, cv2.LINE_AA)
        cv2.circle(canvas, pt, 6, c, -1, cv2.LINE_AA)
    n, el_lm, er_lm = landmarks[0], landmarks[7], landmarks[8]
    if n.visibility > 0.3:
        cx = int((n.x + el_lm.x + er_lm.x) / 3 * w)
        cy = int((n.y + el_lm.y + er_lm.y) / 3 * h)
        r  = max(15, int(abs(el_lm.x - er_lm.x) * w * 0.75))
        cv2.circle(canvas, (cx,cy), r+6, (30,15,60), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx,cy), r, (0,220,255), 2, cv2.LINE_AA)
