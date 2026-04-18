# Camera-Based Full Body Tracking System — Deep Analysis

## 1. Project Overview

**Camera FBT** is a production-grade, camera-based full body tracking system inspired by [SlimeVR](https://slimevr.dev). Unlike SlimeVR which uses IMU sensors strapped to the body, this system achieves full body tracking using only a standard webcam and computer vision. It detects up to 5 people simultaneously, extracts 3D skeletal data, and streams it through a real-time web dashboard and optionally via OSC protocol to VR applications like VRChat.

**Key differentiator**: Zero additional hardware required — webcam only.

---

## 2. Technologies Used

| Technology | Version | Role |
|-----------|---------|------|
| **Python** | 3.9+ | Core runtime, backend processing |
| **MediaPipe** | ≥0.10.0 | Google's ML framework for 33-point 3D pose estimation — extracts world coordinates (meters) from monocular camera input using deep neural networks |
| **OpenCV** | ≥4.8.0 | Camera capture, frame processing, JPEG encoding for streaming |
| **NumPy** | ≥1.24.0 | Array operations for coordinate transforms |
| **FastAPI** | ≥0.100.0 | Async web framework serving the dashboard and WebSocket API |
| **Uvicorn** | ≥0.23.0 | ASGI server running FastAPI |
| **WebSockets** | ≥11.0 | Real-time bidirectional streaming (backend ↔ browser) |
| **Three.js** | r128 | Browser-side 3D skeleton rendering with orbit controls |
| **python-osc** | ≥1.8.0 | VRChat OSC tracker protocol output over UDP |

---

## 3. System Architecture

### 3.1. Data Flow Pipeline

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────────┐
│  Webcam  │───▶│ MediaPipe 3D │───▶│ One-Euro     │───▶│ Skeleton       │
│  30 FPS  │    │ Pose (×5)    │    │ Filter Bank  │    │ Solver         │
└──────────┘    └──────────────┘    └──────────────┘    └───────┬────────┘
                                                                │
                                         ┌──────────────────────┼───────────┐
                                         │                      │           │
                                    ┌────▼────┐          ┌──────▼──────┐   │
                                    │ WebSocket│          │  OSC UDP    │   │
                                    │ Server   │          │  Sender     │   │
                                    └────┬─────┘          └─────────────┘   │
                                         │                                  │
                                    ┌────▼────────────────────────────┐     │
                                    │     Web Dashboard (Browser)     │     │
                                    │  Camera  │  3D Skeleton  │ Ctrl │     │
                                    └─────────────────────────────────┘     │
```

### 3.2. Processing Pipeline (`pipeline.py`)

The pipeline orchestrator follows a strict sequential chain per frame:

1. **Frame Acquisition** — Camera reads BGR frame, horizontally flipped for mirror effect
2. **Pose Detection** — MediaPipe detects up to `num_poses` (default 5) people, returning both:
   - `pose_world_landmarks`: 3D coordinates in meters (hip-centered, real-world scale)
   - `pose_landmarks`: 2D normalized screen coordinates (for overlay drawing)
3. **Per-Person Filtering** — Each person gets an independent bank of 99 One-Euro filters (33 landmarks × 3 axes)
4. **Skeleton Solving** — Filtered 3D landmarks are converted to 8 VR tracker positions + rotations
5. **Output Distribution** — Results fan out to WebSocket (all persons) and OSC (primary person only)

### 3.3. Coordinate System Transform

A critical engineering challenge — converting between two different coordinate systems:

| Axis | MediaPipe World | Unity/VRChat |
|------|----------------|--------------|
| X | Right (+) | Right (+) — **same** |
| Y | Down (+) | Up (+) — **flipped** |
| Z | Forward (+) | Back (+) — **flipped** |
| Handedness | Right-handed | Left-handed |

Transform: `unity_x = mp_x`, `unity_y = -mp_y`, `unity_z = -mp_z`

---

## 4. Methodology & Technical Deep Dive

### 4.1. One-Euro Adaptive Filter

The previous project used a naive Exponential Moving Average (EMA) with fixed alpha. This has a fundamental tradeoff: low alpha = smooth but laggy; high alpha = responsive but jittery.

The **One-Euro filter** (Casiez et al., CHI 2012) solves this by making the cutoff frequency **speed-adaptive**:

```
cutoff = min_cutoff + β × |velocity|
```

- **Stationary** (velocity ≈ 0): cutoff drops to `min_cutoff` → heavy smoothing, no jitter
- **Fast movement** (high velocity): cutoff increases → light smoothing, no lag

Each of the 33 landmarks × 3 axes (X, Y, Z) gets its own independent filter instance = **99 filters per person** × up to 5 persons = **495 concurrent filters**.

### 4.2. Multi-Person Tracking

MediaPipe's Tasks API supports `num_poses > 1`. The system manages this by:

- Maintaining a `dict[int, PoseFilter]` — filter banks keyed by person index
- Creating new filter instances when new persons appear
- Garbage-collecting stale filter instances when persons leave the frame
- Color-coding each person in the dashboard (cyan, magenta, green, orange, yellow)

### 4.3. VRChat OSC Protocol

Per the [VRChat OSC Trackers spec](https://docs.vrchat.com/docs/osc-trackers):

- **8 tracker slots**: hip, chest, 2× feet, 2× knees, 2× elbows
- **1 head alignment** tracker for space calibration
- Each tracker sends **position** (Vector3 meters) and **rotation** (Euler degrees, Z→X→Y order)
- Data sent as UDP packets to VRChat's OSC receiver (default port 9000)

### 4.4. T-Pose Calibration

Calibration solves the scaling problem between MediaPipe's internal skeletal model and real-world measurements:

1. User stands in T-pose (arms extended horizontally)
2. System measures: shoulder width, arm length, leg length, torso length
3. Computes `scale_factor = real_height / mediapipe_height`
4. Determines floor offset (so feet sit at Y=0 in VR)
5. Saves profile as JSON for persistence across sessions

### 4.5. Real-Time Web Dashboard

The dashboard uses a decoupled architecture:
- **Backend thread**: captures frames, runs ML inference, produces results at ~30 FPS
- **FastAPI server**: serves static files + WebSocket endpoint
- **WebSocket protocol**: streams JSON at 30 FPS containing:
  - Base64-encoded JPEG camera frame with skeleton overlay
  - Per-person landmark arrays (33 × {x, y, z, visibility})
  - Per-person tracker data (position + rotation per tracker)
  - Performance metrics (FPS, latency, person count)
- **Three.js renderer**: draws 3D skeletons with orbit camera controls
- **Bidirectional commands**: dashboard sends calibration/filter/OSC commands back to server

---

## 5. Module Architecture

| Module | Lines | Responsibility |
|--------|-------|---------------|
| `models.py` | ~130 | Data classes, enums, serialization |
| `config.py` | ~100 | Configuration with env var + CLI support |
| `detector.py` | ~140 | MediaPipe backend abstraction (Tasks/legacy) |
| `filters.py` | ~120 | One-Euro filter implementation |
| `skeleton.py` | ~170 | 3D landmark → VR tracker conversion |
| `calibration.py` | ~130 | T-pose measurement + persistence |
| `osc_sender.py` | ~80 | VRChat OSC UDP protocol |
| `pipeline.py` | ~110 | Processing chain orchestrator |
| `server.py` | ~190 | FastAPI server + capture thread |
| `web/` | ~700 | Dashboard (HTML + CSS + JS) |
| **Total** | ~1870 | |

---

## 6. Future Scope

1. **Multi-Camera Fusion** — Using 2+ cameras at different angles to dramatically improve Z-depth accuracy (stereo reconstruction)
2. **Hand/Finger Tracking** — MediaPipe Hands integration for fine-grained finger tracking alongside body
3. **Recording & Playback** — Record tracking sessions as `.bvh` (BioVision Hierarchy) files for animation import into Blender/Unity
4. **GPU Acceleration** — ONNX Runtime or TensorRT backends for higher FPS on GPU-equipped machines
5. **Mobile App** — React Native / Flutter client streaming to PC over WiFi
6. **Gesture Recognition** — Posture classifier (T-pose, wave, squat) using the tracked skeleton data for VR avatar control
7. **Depth Camera Support** — Intel RealSense / Azure Kinect integration for true metric depth instead of monocular estimation

---

## 7. Known Limitations

- **Z-depth accuracy**: Monocular (single camera) 3D estimation is inherently less accurate for depth (Z-axis) than X/Y
- **Occlusion**: Tracking quality degrades when body parts are hidden behind other objects
- **Lighting**: Low-light environments reduce MediaPipe's detection confidence
- **Camera placement**: Best results with full-body view from 2–4 meters distance
