# Camera FBT — Camera-Based Full Body Tracking

Real-time full body tracking using a webcam and MediaPipe, inspired by [SlimeVR](https://slimevr.dev). Tracks up to 5 people simultaneously and streams skeletal data via a live web dashboard — no VR headset required.

---

## How It Works

```
Webcam → MediaPipe 3D Pose → One-Euro Filter → Skeleton Solver → Web Dashboard
                                                                 → OSC Output (optional)
```

1. **Camera captures** video at 30 FPS
2. **MediaPipe** extracts 33 3D body landmarks per person (meter-scale world coordinates)
3. **One-Euro Filter** removes jitter while preserving fast movements
4. **Skeleton Solver** converts landmarks into 8 VR tracker positions + rotations
5. **Web Dashboard** renders everything in real-time via WebSocket + Three.js
6. **OSC Output** (optional) streams tracker data to VRChat/SteamVR

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

Dashboard opens at **http://localhost:8765**

### CLI Options

```bash
python main.py --camera 1              # Use second camera
python main.py --height 177.8          # Set your height (cm)
python main.py --poses 3               # Track up to 3 people
python main.py --osc --osc-ip 127.0.0.1 --osc-port 9000  # Enable VRChat OSC
python main.py --port 9090             # Custom dashboard port
```

---

## Project Structure

```
camera-fbt/
├── main.py                 ← CLI entry point
├── pyproject.toml           ← PEP 621 packaging
├── requirements.txt         ← Dependencies
├── pose_landmarker.task     ← MediaPipe model weights
├── src/
│   ├── config.py            ← Centralized configuration (dataclass + env)
│   ├── models.py            ← Data classes (Landmark3D, TrackerData, etc.)
│   ├── detector.py          ← MediaPipe 3D pose detection (multi-person)
│   ├── filters.py           ← One-Euro adaptive smoothing filter
│   ├── skeleton.py          ← Landmark → VR tracker solver
│   ├── calibration.py       ← T-pose calibration + body proportions
│   ├── osc_sender.py        ← VRChat OSC UDP transmitter
│   ├── pipeline.py          ← Processing pipeline orchestrator
│   └── server.py            ← FastAPI + WebSocket server
├── web/
│   ├── index.html           ← Dashboard (3-panel layout)
│   ├── css/dashboard.css    ← Dark theme + glassmorphism
│   └── js/
│       ├── app.js           ← WebSocket handler + UI bindings
│       ├── skeleton3d.js    ← Three.js 3D skeleton renderer
│       └── metrics.js       ← Performance metrics panel
└── tests/
    ├── test_config.py       ← Configuration validation tests
    ├── test_filters.py      ← One-Euro filter convergence tests
    └── test_skeleton.py     ← Coordinate transform + solver tests
```

---

## Dashboard Features

| Feature | Description |
|---------|-------------|
| **Camera Feed** | Live view with skeleton overlay, color-coded per person |
| **3D Skeleton** | Interactive Three.js viewer with orbit controls |
| **Performance** | Real-time FPS and latency gauges |
| **Tracker Status** | 9 tracker dots (hip, chest, feet, knees, elbows, head) |
| **Calibration** | T-pose button with 3-second countdown |
| **Filter Tuning** | Live sliders for jitter reduction / responsiveness |
| **OSC Control** | Toggle on/off, configure IP + port |

---

## VRChat OSC Integration

When OSC is enabled, the system sends tracker data per the [VRChat OSC Trackers spec](https://docs.vrchat.com/docs/osc-trackers):

| Tracker | OSC Address | Body Part |
|---------|------------|-----------|
| #1 | `/tracking/trackers/1/position` + `/rotation` | Hip |
| #2 | `/tracking/trackers/2/position` + `/rotation` | Chest |
| #3 | `/tracking/trackers/3/position` + `/rotation` | Left Foot |
| #4 | `/tracking/trackers/4/position` + `/rotation` | Right Foot |
| #5 | `/tracking/trackers/5/position` + `/rotation` | Left Knee |
| #6 | `/tracking/trackers/6/position` + `/rotation` | Right Knee |
| #7 | `/tracking/trackers/7/position` + `/rotation` | Left Elbow |
| #8 | `/tracking/trackers/8/position` + `/rotation` | Right Elbow |
| head | `/tracking/trackers/head/position` + `/rotation` | Head |

Each sends Vector3 (3 floats) in Unity's left-handed coordinate system (+Y up, 1.0 = 1 meter).

---

## Tech Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.9+ | Backend runtime |
| MediaPipe | 33-point 3D pose estimation |
| OpenCV | Webcam capture + frame processing |
| NumPy | Array operations |
| FastAPI | WebSocket server + static file serving |
| Three.js | Browser-based 3D skeleton visualization |
| python-osc | VRChat OSC protocol output |

---

## Configuration

All settings configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FBT_CAMERA` | `0` | Camera device index |
| `FBT_WIDTH` / `FBT_HEIGHT` | `640` / `480` | Resolution |
| `FBT_NUM_POSES` | `5` | Max persons to track |
| `FBT_HEIGHT_CM` | `177.8` | Your height in cm |
| `FBT_FILTER_MINCUTOFF` | `1.7` | Jitter reduction (lower = smoother) |
| `FBT_FILTER_BETA` | `0.007` | Responsiveness (higher = less lag) |
| `FBT_OSC_ENABLED` | `false` | Enable OSC output |
| `FBT_OSC_IP` | `127.0.0.1` | OSC target IP |
| `FBT_OSC_PORT` | `9000` | OSC target port |
| `FBT_PORT` | `8765` | Dashboard server port |

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## License

MIT
