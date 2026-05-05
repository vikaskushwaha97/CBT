# Camera FBT v2.0 — Hybrid Full Body Tracking

Real-time full body tracking combining a **webcam + ESP32/MPU-6050 IMU sensors**, inspired by [SlimeVR](https://slimevr.dev). Works in three modes:

| Mode | Hardware | Quality |
|------|----------|---------|
| **Camera Only** | Webcam alone | Good — zero extra hardware |
| **Hybrid** | Webcam + IMU sensors | Best — accurate rotation, drift-free |
| **IMU Only** *(coming)* | Sensors alone | Good — fully wireless |

Tracks up to 5 people, streams skeletal data via a live web dashboard, and outputs to VRChat/SteamVR over OSC — all in real-time.

---

## How It Works

### Camera-Only Mode
```
Webcam → MediaPipe 3D Pose → One-Euro Filter → Skeleton Solver → Web Dashboard
                                                                 → OSC Output
```

### Hybrid Mode (Camera + IMU)
```
Webcam → MediaPipe 3D Pose ──────────────────────────┐
                             ↓                        ↓
ESP32/MPU-6050 → UDP ──→ IMU Receiver ──→ Rotation Override → Skeleton Solver
                              ↑ yaw correction feedback ↗
                                                          ↓
                                                   Web Dashboard + OSC
```

**Why hybrid?**
- Camera provides accurate **position** (X, Y) and **yaw correction**
- MPU-6050 provides accurate **pitch + roll** (no drift on these axes)
- Camera corrects MPU-6050 **yaw drift** (6-DOF IMUs have no magnetometer) each frame via a complementary filter

---

## Quick Start

### Camera-Only (no hardware needed)
```bash
pip install -r requirements.txt
python main.py
```

### Hybrid Mode (with ESP32 + MPU-6050 sensors)
```bash
# 1. Flash firmware onto each ESP32 (see firmware/esp32_mpu6050/README.md)
# 2. Run with IMU enabled
python main.py --imu --imu-port 6969 --imu-count 3
```

Dashboard opens at **http://localhost:8765**

---

## CLI Reference

```bash
# Camera
python main.py --camera 1              # Use second camera
python main.py --height 177.8          # Your height in cm (for scaling)
python main.py --poses 3               # Track up to 3 people

# IMU Sensors
python main.py --imu                   # Enable IMU fusion (default port 6969)
python main.py --imu --imu-port 6969   # Specify UDP listen port
python main.py --imu --imu-count 5     # Expected number of sensors

# OSC Output
python main.py --osc                   # Enable VRChat OSC (127.0.0.1:9000)
python main.py --osc --osc-ip 192.168.1.5 --osc-port 9000

# Combined example
python main.py --imu --osc --height 175 --camera 0

# Dashboard port
python main.py --port 9090
```

---

## IMU Sensor Setup (ESP32 + MPU-6050)

### Hardware Per Node (~$5 total)

| Component | Notes |
|-----------|-------|
| ESP32 Dev Board | Any 30-pin variant (NodeMCU-32S, DOIT, etc.) |
| GY-521 MPU-6050 module | 6-DOF: 3-axis gyro + 3-axis accelerometer |

### Wiring
```
MPU-6050   →   ESP32
VCC        →   3.3V
GND        →   GND
SDA        →   GPIO 21
SCL        →   GPIO 22
INT        →   GPIO 15
AD0        →   GND  (I²C address 0x68)
```

### Sensor Placement

| ID | Body Part | Priority |
|----|-----------|----------|
| 0 | **Hip** (pelvis center) | 🔴 Critical |
| 1 | Chest (upper torso) | 🟠 High |
| 2 | Left Thigh | 🟡 Medium |
| 3 | Right Thigh | 🟡 Medium |
| 4 | **Left Ankle** | 🔴 Critical |
| 5 | **Right Ankle** | 🔴 Critical |
| 6 | Left Wrist | 🟢 Optional |
| 7 | Right Wrist | 🟢 Optional |

**Minimum viable: 3 sensors** → Hip (0) + Left Ankle (4) + Right Ankle (5)

### Firmware

Each ESP32 runs `firmware/esp32_mpu6050/esp32_mpu6050.ino`. Edit four lines before flashing:

```cpp
#define WIFI_SSID   "your_network"
#define WIFI_PASS   "your_password"
#define SERVER_IP   "192.168.x.x"   // Your PC's local IP
#define SENSOR_ID   0               // Unique ID per sensor (0-7)
```

See [`firmware/esp32_mpu6050/README.md`](firmware/esp32_mpu6050/README.md) for full wiring + calibration guide.

---

## Project Structure

```
camera-fbt/
├── main.py                    ← CLI entry point (--imu, --osc, --camera, ...)
├── pyproject.toml             ← PEP 621 packaging (v2.0.0)
├── requirements.txt           ← Python dependencies
├── pose_landmarker.task       ← MediaPipe model weights
│
├── src/
│   ├── config.py              ← AppConfig (env vars + CLI args, including IMU)
│   ├── models.py              ← Data classes: Landmark3D, IMUReading, SensorState, ...
│   ├── detector.py            ← MediaPipe 3D pose detection (multi-person)
│   ├── filters.py             ← One-Euro adaptive smoothing filter (99 per person)
│   ├── skeleton.py            ← Landmark → VR tracker solver (pitch, yaw, roll)
│   ├── calibration.py         ← T-pose calibration + body proportions
│   ├── osc_sender.py          ← VRChat OSC UDP transmitter
│   ├── pipeline.py            ← Orchestrator: camera + optional IMU fusion
│   ├── server.py              ← FastAPI + WebSocket server
│   └── sources/
│       ├── __init__.py
│       └── imu_source.py      ← UDP receiver for ESP32/MPU-6050 packets
│
├── web/
│   ├── index.html             ← Dashboard (3-panel: camera / 3D skeleton / controls)
│   ├── css/dashboard.css      ← Dark glassmorphism theme
│   └── js/
│       ├── app.js             ← WebSocket handler + UI bindings
│       ├── skeleton3d.js      ← Three.js 3D skeleton renderer
│       └── metrics.js         ← Metrics + tracker + IMU sensor status panel
│
├── firmware/
│   └── esp32_mpu6050/
│       ├── esp32_mpu6050.ino  ← Arduino firmware (DMP mode, WiFi UDP)
│       └── README.md          ← Wiring + calibration + setup guide
│
└── tests/
    ├── test_config.py         ← Configuration validation tests
    ├── test_filters.py        ← One-Euro filter convergence tests
    └── test_skeleton.py       ← Coordinate transform + solver tests
```

---

## Dashboard Features

| Feature | Description |
|---------|-------------|
| **Camera Feed** | Live view with skeleton overlay, color-coded per person |
| **3D Skeleton** | Interactive Three.js viewer (Front / Side / Top) |
| **Performance** | Real-time FPS and latency gauges |
| **Tracker Status** | 9 tracker dots (hip, chest, feet, knees, elbows, head) |
| **IMU Sensors** | Live panel: each sensor's connection state, latency, packet count |
| **Mode Badge** | Header shows `Camera Only` or `Hybrid ★` when sensors active |
| **Calibration** | T-pose button with 3-second countdown |
| **Filter Tuning** | Live sliders for jitter reduction / responsiveness |
| **OSC Control** | Toggle on/off, configure IP + port |

---

## VRChat OSC Integration

Enable with `--osc`. Sends per the [VRChat OSC Trackers spec](https://docs.vrchat.com/docs/osc-trackers):

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

In **hybrid mode**, rotations sent over OSC come from the IMU sensors (more accurate than camera-only estimates).

---

## Tech Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.9+ | Backend runtime |
| MediaPipe ≥ 0.10 | 33-point 3D pose estimation (multi-person) |
| OpenCV | Webcam capture + JPEG streaming |
| NumPy | Array operations |
| FastAPI + Uvicorn | Async WebSocket server |
| Three.js r128 | Browser 3D skeleton renderer |
| python-osc | VRChat OSC UDP protocol |
| ESP32 Arduino | WiFi microcontroller for sensor nodes |
| MPU-6050 DMP | Onboard quaternion computation (Jeff Rowberg library) |

---

## Configuration

All settings via environment variables (or CLI args — CLI takes priority):

### Camera & Detection
| Variable | Default | Description |
|----------|---------|-------------|
| `FBT_CAMERA` | `0` | Camera device index |
| `FBT_WIDTH` / `FBT_HEIGHT` | `640` / `480` | Resolution |
| `FBT_NUM_POSES` | `5` | Max persons to track |
| `FBT_HEIGHT_CM` | `177.8` | Your height (cm) for scale |

### Filtering
| Variable | Default | Description |
|----------|---------|-------------|
| `FBT_FILTER_MINCUTOFF` | `1.7` | Jitter reduction (↓ = smoother) |
| `FBT_FILTER_BETA` | `0.007` | Responsiveness (↑ = less lag) |

### IMU Sensors
| Variable | Default | Description |
|----------|---------|-------------|
| `FBT_IMU_ENABLED` | `false` | Enable IMU receiver |
| `FBT_IMU_PORT` | `6969` | UDP listen port |
| `FBT_IMU_COUNT` | `3` | Expected sensor count |
| `FBT_IMU_YAW_ALPHA` | `0.97` | Complementary filter weight (0=camera, 1=IMU) |
| `FBT_SOURCE_MODE` | `camera` | `camera` / `hybrid` / `imu` |

### OSC & Server
| Variable | Default | Description |
|----------|---------|-------------|
| `FBT_OSC_ENABLED` | `false` | Enable OSC output |
| `FBT_OSC_IP` | `127.0.0.1` | OSC target IP |
| `FBT_OSC_PORT` | `9000` | OSC target port |
| `FBT_PORT` | `8765` | Dashboard server port |

---

## IMU Packet Protocol

Each ESP32 sends a **48-byte UDP packet** at ~100 Hz (little-endian):

| Offset | Type | Field |
|--------|------|-------|
| 0-1 | uint8 × 2 | Magic bytes `0xCA 0xFE` |
| 2 | uint8 | Sensor ID (0–7) |
| 3 | uint8 | Packet type (`0x01`) |
| 4–19 | float32 × 4 | Quaternion: w, x, y, z (from DMP) |
| 20–31 | float32 × 3 | Linear accel: ax, ay, az (g, gravity removed) |
| 32–43 | float32 × 3 | Gyro: gx, gy, gz (deg/s) |
| 44–47 | uint32 | `millis()` timestamp |

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## License

MIT
