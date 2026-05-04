# ESP32 + MPU-6050 Sensor Node — Setup Guide

This directory contains the Arduino firmware for one sensor node.
Each node is an **ESP32 dev board** wired to a **MPU-6050 (GY-521)** module,
running DMP mode to output quaternions at ~100 Hz over WiFi UDP.

---

## Hardware Required (per sensor)

| Component | Cost | Notes |
|-----------|------|-------|
| ESP32 Dev Board (any 30-pin variant) | ~$4 | NodeMCU-32S, DOIT, etc. |
| GY-521 MPU-6050 module | ~$1 | Includes pull-up resistors |
| Breadboard + jumper wires | ~$1 | For prototyping |
| Hot glue / velcro | — | For attaching to body |

**Minimum viable build: 3 nodes** → HIP + LEFT_ANKLE + RIGHT_ANKLE

---

## Wiring

```
MPU-6050 (GY-521)     ESP32
─────────────────     ─────────────────
VCC              →    3.3V
GND              →    GND
SDA              →    GPIO 21  (I²C SDA)
SCL              →    GPIO 22  (I²C SCL)
INT              →    GPIO 15  (DMP interrupt)
AD0              →    GND      (sets I²C address to 0x68)
```

> ⚠️ **Use 3.3V only** — MPU-6050 is 3.3V tolerant on I/O but VCC must be 3.3V on most ESP32 boards. Do NOT connect VCC to 5V if using the ESP32's 3.3V output.

---

## Arduino IDE Setup

### 1 — Install ESP32 Board Support
1. File → Preferences → Additional Board Manager URLs, add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
2. Tools → Board Manager → search **esp32** → Install **esp32 by Espressif Systems**

### 2 — Install Required Libraries (Sketch → Include Library → Manage Libraries)

| Library | Author | Version |
|---------|--------|---------|
| **I2Cdev** | Jeff Rowberg | any |
| **MPU6050** | Jeff Rowberg | any (must include MotionApps612) |

> If the Library Manager version doesn't include `MPU6050_6Axis_MotionApps612.h`, clone from:
> `https://github.com/jrowberg/i2cdevlib/tree/master/Arduino/MPU6050`

### 3 — Configure the Firmware

Open `esp32_mpu6050.ino` and edit the four lines at the top:

```cpp
#define WIFI_SSID   "your_network_name"
#define WIFI_PASS   "your_wifi_password"
#define SERVER_IP   "192.168.x.x"     // Find with: ipconfig (Windows) / ip addr (Linux)
#define SENSOR_ID   0                 // See table below — different for each ESP32
```

### 4 — Sensor ID Assignment

Flash each ESP32 with a unique `SENSOR_ID` before attaching to the body:

| ID | Body Part | Priority |
|----|-----------|----------|
| 0 | Hip (pelvis center) | 🔴 Critical |
| 1 | Chest (upper torso) | 🟠 High |
| 2 | Left Thigh | 🟡 Medium |
| 3 | Right Thigh | 🟡 Medium |
| 4 | Left Ankle | 🔴 Critical |
| 5 | Right Ankle | 🔴 Critical |
| 6 | Left Wrist | 🟢 Optional |
| 7 | Right Wrist | 🟢 Optional |

### 5 — Flash

- Tools → Board → **ESP32 Dev Module**
- Tools → Port → select the COM port of your ESP32
- Upload (Ctrl+U)
- Open Serial Monitor (115200 baud) to verify DMP init and WiFi connection

---

## Gyroscope Calibration

The firmware calls `mpu.CalibrateAccel(6)` and `mpu.CalibrateGyro(6)` automatically on boot.
Keep the sensor **flat and still** for ~6 seconds during startup (while the LED blinks slowly).

For better accuracy, run the separate **MPU6050_calibration** sketch first, note the offsets,
and hardcode them in the firmware:

```cpp
mpu.setXGyroOffset(220);
mpu.setYGyroOffset(76);
mpu.setZGyroOffset(-85);
mpu.setXAccelOffset(-1788);
mpu.setYAccelOffset(-240);
mpu.setZAccelOffset(1420);
```

---

## Sensor Placement Guide

Attach sensors **firmly** to the body — movement between sensor and skin causes noise.

```
         [HEAD] ← optional, use VR headset IMU instead
           │
     [CHEST] ← strap to sternum, sensor facing forward
           │
       [HIP] ← belt clip at small of back, sensor facing up
      /        \
[L_THIGH]   [R_THIGH] ← front of thigh, mid-way
    │               │
[L_ANKLE]   [R_ANKLE] ← above ankle bone, sensor facing up
```

**Orientation**: All sensors should ideally face the same direction
(sensor Z-axis pointing upward or forward consistently). The DMP handles
arbitrary mounting orientation after yaw correction from the camera.

---

## Running the Full System

### Terminal 1 — Start the tracker (camera + IMU hybrid mode)
```bash
cd mini-project-sem-6
python main.py --imu --imu-port 6969 --imu-count 3
```

### Terminal 2 (optional) — Monitor incoming sensor packets
```powershell
# Windows — listen on UDP 6969 to verify sensors are sending
# (built into the server, check the console log for "New IMU sensor connected: id=X")
```

### Dashboard
Open `http://localhost:8765` — the Sensors panel shows each node's connection
status and latency once they start sending data.

---

## Protocol Reference

Each ESP32 sends a **48-byte UDP packet** at ~100 Hz:

| Offset | Type | Field | Description |
|--------|------|-------|-------------|
| 0 | uint8 | magic_h | 0xCA |
| 1 | uint8 | magic_l | 0xFE |
| 2 | uint8 | sensor_id | Body part (0-7) |
| 3 | uint8 | ptype | 0x01 |
| 4-19 | float32×4 | qw, qx, qy, qz | DMP quaternion |
| 20-31 | float32×3 | ax, ay, az | Linear accel (g, gravity removed) |
| 32-43 | float32×3 | gx, gy, gz | Gyro (deg/s) |
| 44-47 | uint32 | ts_ms | ESP32 millis() |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| LED fast-blinking forever | MPU-6050 not found | Check SDA/SCL wiring; try 5V VCC |
| Serial: "DMP Init failed code 1" | I²C address conflict | Check AD0 → GND connection |
| Serial: "WiFi FAILED" | Wrong SSID/pass | Verify credentials; 2.4GHz only |
| Sensor shows in dashboard but jittery | Poor mounting | Use velcro + cable tie to secure |
| Yaw drifts even with camera | Camera occluded | Ensure camera can see shoulders |
