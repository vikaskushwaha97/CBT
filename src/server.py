"""
server.py — FastAPI + WebSocket server for the tracking dashboard.

Serves the web dashboard and streams skeleton data in real-time via WebSocket.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import traceback
from typing import Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.camera import CameraCapture
from src.config import AppConfig
from src.models import LandmarkIndex as LI
from src.pipeline import TrackingPipeline

logger = logging.getLogger(__name__)

# ── Globals shared between capture thread and server ─────────────────────────
_latest_result = None
_latest_frame_b64 = None
_pipeline: Optional[TrackingPipeline] = None
_camera: Optional[CameraCapture] = None
_config: Optional[AppConfig] = None
_running = False
_lock = threading.Lock()
_capture_errors = 0

PERSON_COLORS = [
    (0, 255, 255), (255, 0, 255), (0, 255, 0),
    (255, 165, 0), (255, 255, 0),
]

SKELETON_CONNECTIONS = [
    (LI.LEFT_SHOULDER, LI.RIGHT_SHOULDER),
    (LI.LEFT_SHOULDER, LI.LEFT_ELBOW),
    (LI.LEFT_ELBOW, LI.LEFT_WRIST),
    (LI.RIGHT_SHOULDER, LI.RIGHT_ELBOW),
    (LI.RIGHT_ELBOW, LI.RIGHT_WRIST),
    (LI.LEFT_SHOULDER, LI.LEFT_HIP),
    (LI.RIGHT_SHOULDER, LI.RIGHT_HIP),
    (LI.LEFT_HIP, LI.RIGHT_HIP),
    (LI.LEFT_HIP, LI.LEFT_KNEE),
    (LI.LEFT_KNEE, LI.LEFT_ANKLE),
    (LI.RIGHT_HIP, LI.RIGHT_KNEE),
    (LI.RIGHT_KNEE, LI.RIGHT_ANKLE),
    (LI.NOSE, LI.LEFT_EYE),
    (LI.NOSE, LI.RIGHT_EYE),
    (LI.LEFT_EAR, LI.LEFT_EYE),
    (LI.RIGHT_EAR, LI.RIGHT_EYE),
]


def _draw_skeleton_overlay(frame: np.ndarray, result) -> np.ndarray:
    """Draw skeleton overlay on camera frame for all detected persons."""
    try:
        overlay = frame.copy()
        h, w = overlay.shape[:2]

        for person in result.persons:
            color = PERSON_COLORS[person.person_id % len(PERSON_COLORS)]
            lms = person.landmarks
            if not lms:
                continue

            for a, b in SKELETON_CONNECTIONS:
                if a < len(lms) and b < len(lms):
                    la, lb = lms[a], lms[b]
                    if la.visibility > 0.3 and lb.visibility > 0.3:
                        p1 = (int(la.x * w), int(la.y * h))
                        p2 = (int(lb.x * w), int(lb.y * h))
                        cv2.line(overlay, p1, p2, (255, 255, 255), 6, cv2.LINE_AA)
                        cv2.line(overlay, p1, p2, color, 4, cv2.LINE_AA)

            for j, lm in enumerate(lms):
                if lm.visibility > 0.3:
                    pt = (int(lm.x * w), int(lm.y * h))
                    cv2.circle(overlay, pt, 6, (255, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(overlay, pt, 4, color, -1, cv2.LINE_AA)

            if len(lms) > LI.NOSE and lms[LI.NOSE].visibility > 0.3:
                np_ = (int(lms[LI.NOSE].x * w), int(lms[LI.NOSE].y * h) - 20)
                cv2.putText(
                    overlay, f"P{person.person_id}",
                    np_, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA
                )

        cv2.putText(
            overlay, f"FPS: {result.fps:.1f} | Lat: {result.latency_ms:.1f}ms",
            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA
        )
        cv2.putText(
            overlay, f"Persons: {result.num_persons}",
            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA
        )
        return overlay
    except Exception as e:
        logger.debug("Overlay error: %s", e)
        return frame


# ── Capture thread ───────────────────────────────────────────────────────────
def _capture_loop():
    """Runs in a background thread: capture → process → store."""
    global _latest_result, _latest_frame_b64, _running, _capture_errors

    logger.info("Capture thread started.")
    consecutive_failures = 0
    max_failures = 30  # ~1 second of failures before attempting recovery

    while _running:
        try:
            # Check camera health
            if not _camera.is_opened:
                logger.warning("Camera lost, attempting to reopen...")
                try:
                    _camera.close()
                    time.sleep(1.0)
                    _camera.open()
                    consecutive_failures = 0
                    logger.info("Camera reopened successfully.")
                except Exception as e:
                    logger.error("Camera reopen failed: %s", e)
                    time.sleep(2.0)
                    continue

            frame = _camera.read()
            if frame is None:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    logger.warning("Too many frame failures (%d), attempting camera recovery...", consecutive_failures)
                    try:
                        _camera.close()
                        time.sleep(1.0)
                        _camera.open()
                        consecutive_failures = 0
                    except Exception:
                        time.sleep(2.0)
                else:
                    time.sleep(0.01)
                continue

            consecutive_failures = 0
            result = _pipeline.process_frame(frame)
            overlay = _draw_skeleton_overlay(frame, result)

            _, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            with _lock:
                _latest_result = result
                _latest_frame_b64 = frame_b64

            # Rate limiting — target ~25 FPS processing
            time.sleep(0.005)

        except Exception as e:
            _capture_errors += 1
            logger.error("Capture error #%d: %s", _capture_errors, e)
            if _capture_errors > 100:
                logger.critical("Too many capture errors, stopping capture thread.")
                break
            time.sleep(0.1)

    logger.info("Capture thread stopped.")


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="Camera FBT Dashboard", version="1.0.0")

# Serve static files
_web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.isdir(_web_dir):
    app.mount("/static", StaticFiles(directory=_web_dir), name="static")


@app.on_event("startup")
async def startup():
    global _pipeline, _camera, _config, _running

    # Use the config set by run_server(), or create default
    if _config is None:
        _config = AppConfig()

    _pipeline = TrackingPipeline(_config)
    _camera = CameraCapture(_config)
    _camera.open()
    _running = True

    thread = threading.Thread(target=_capture_loop, daemon=True)
    thread.start()
    logger.info("Server started, dashboard at http://localhost:%d", _config.server_port)


@app.on_event("shutdown")
async def shutdown():
    global _running
    _running = False
    time.sleep(0.2)  # let capture thread finish
    if _camera:
        _camera.close()
    if _pipeline:
        _pipeline.close()


@app.get("/")
async def index():
    """Serve the main dashboard page."""
    index_path = os.path.join(_web_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard not found</h1>")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Stream tracking data + camera frame via WebSocket."""
    await ws.accept()
    logger.info("WebSocket client connected.")

    try:
        while _running:
            with _lock:
                result = _latest_result
                frame_b64 = _latest_frame_b64

            if result is not None:
                try:
                    payload = result.to_dict()
                    payload["frame"] = frame_b64
                    await ws.send_text(json.dumps(payload))
                except Exception:
                    break  # client disconnected

            # Check for incoming commands (non-blocking)
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.04)
                await _handle_command(msg, ws)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)

    logger.info("WebSocket client disconnected.")


async def _handle_command(msg: str, ws: WebSocket):
    """Handle dashboard commands received via WebSocket."""
    try:
        cmd = json.loads(msg)
        action = cmd.get("action")

        if action == "calibrate":
            if _latest_result and _latest_result.persons:
                frame = _camera.read()
                if frame is not None:
                    world_poses = _pipeline.detector.detect(frame)
                    if world_poses:
                        success = _pipeline.calibrate(world_poses[0])
                        await ws.send_text(json.dumps({
                            "event": "calibration_result",
                            "success": success,
                        }))
                        return
            await ws.send_text(json.dumps({
                "event": "calibration_result",
                "success": False,
                "error": "No person detected",
            }))

        elif action == "toggle_osc":
            enabled = cmd.get("enabled", False)
            ip = cmd.get("ip", "127.0.0.1")
            port = cmd.get("port", 9000)
            success = _pipeline.toggle_osc(enabled, ip, port)
            await ws.send_text(json.dumps({
                "event": "osc_status",
                "active": success and enabled,
            }))

        elif action == "update_filter":
            min_cutoff = cmd.get("min_cutoff")
            beta = cmd.get("beta")
            _pipeline.update_filter_params(
                min_cutoff=float(min_cutoff) if min_cutoff else None,
                beta=float(beta) if beta else None,
            )

    except Exception as e:
        logger.warning("Command error: %s", e)


def run_server(config: AppConfig):
    """Start the uvicorn server."""
    global _config
    _config = config
    uvicorn.run(
        "src.server:app",
        host=config.server_host,
        port=config.server_port,
        log_level="info",
        reload=False,
    )
