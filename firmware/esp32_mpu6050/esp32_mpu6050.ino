/*
 * esp32_mpu6050.ino — ESP32 + MPU-6050 Sensor Node Firmware
 * ===========================================================
 * Reads MPU-6050 via I²C in DMP mode (Jeff Rowberg's library),
 * then streams quaternion + raw IMU data over WiFi UDP to the
 * Python tracking server in the 48-byte binary protocol.
 *
 * Hardware
 * --------
 *   ESP32 Dev Board  (any variant with WiFi)
 *   MPU-6050 module  (GY-521 breakout)
 *
 * Wiring
 * ------
 *   MPU-6050  →  ESP32
 *   VCC       →  3.3V
 *   GND       →  GND
 *   SDA       →  GPIO 21 (default I²C SDA)
 *   SCL       →  GPIO 22 (default I²C SCL)
 *   INT       →  GPIO 15 (DMP interrupt)
 *   AD0       →  GND     (I²C address 0x68)
 *
 * Libraries Required (install via Arduino Library Manager)
 * --------------------------------------------------------
 *   1. "I2Cdev"        by Jeff Rowberg
 *   2. "MPU6050"       by Jeff Rowberg  (must be the _MotionApps version)
 *   3. (built-in)      WiFi, WiFiUdp
 *
 * ─────────────────────────────────────────────────────────
 * CONFIGURE THE FOUR VALUES BELOW BEFORE FLASHING
 * ─────────────────────────────────────────────────────────
 */

// ── User configuration ───────────────────────────────────────────────────────
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASS     "YOUR_WIFI_PASSWORD"
#define SERVER_IP     "192.168.1.100"   // IP of the PC running main.py
#define SERVER_PORT   6969              // Must match --imu-port (default 6969)

/*
 * SENSOR_ID: physical body placement of THIS sensor node.
 * Flash a different ID onto each ESP32 before attaching to the body.
 *
 *   0 = HIP          (most important — pelvis center)
 *   1 = CHEST        (upper torso)
 *   2 = LEFT_THIGH   (left knee direction)
 *   3 = RIGHT_THIGH  (right knee direction)
 *   4 = LEFT_ANKLE   (left foot orientation)
 *   5 = RIGHT_ANKLE  (right foot orientation)
 *   6 = LEFT_WRIST   (left elbow direction)
 *   7 = RIGHT_WRIST  (right elbow direction)
 *
 * Minimum viable set: 0 (HIP) + 4 (LEFT_ANKLE) + 5 (RIGHT_ANKLE)
 */
#define SENSOR_ID     0

// ── Includes ─────────────────────────────────────────────────────────────────
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps612.h"

// ── Protocol constants (must match imu_source.py) ───────────────────────────
#define MAGIC_H    0xCA
#define MAGIC_L    0xFE
#define PTYPE_IMU  0x01
#define INT_PIN    15           // GPIO connected to MPU-6050 INT

// ── 48-byte packet structure (little-endian, packed) ─────────────────────────
#pragma pack(push, 1)
struct IMUPacket {
    uint8_t  magic_h;       // 0xCA
    uint8_t  magic_l;       // 0xFE
    uint8_t  sensor_id;     // SensorID (0-7)
    uint8_t  ptype;         // 0x01
    float    qw, qx, qy, qz;       // DMP quaternion
    float    ax, ay, az;            // Linear accel (g, gravity removed)
    float    gx, gy, gz;            // Gyro (deg/s)
    uint32_t ts_ms;                 // millis()
};
#pragma pack(pop)

static_assert(sizeof(IMUPacket) == 48, "Packet size mismatch — check struct packing");

// ── Globals ───────────────────────────────────────────────────────────────────
MPU6050 mpu;
WiFiUDP udp;

// DMP state
bool     dmpReady    = false;
uint8_t  devStatus   = 0;
uint16_t packetSize  = 0;
volatile bool mpuInterrupt = false;

// DMP output buffers
Quaternion   q;
VectorFloat  gravity;
VectorInt16  aa, aaReal, gg;
uint8_t      fifoBuffer[64];

// LED feedback (GPIO 2 on most ESP32 boards)
#define LED_PIN 2

// ── Interrupt handler ─────────────────────────────────────────────────────────
void IRAM_ATTR dmpDataReady() {
    mpuInterrupt = true;
}

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    Serial.println("\n=== ESP32 + MPU-6050 Sensor Node ===");
    Serial.printf("Sensor ID : %d\n", SENSOR_ID);
    Serial.printf("Server    : %s:%d\n", SERVER_IP, SERVER_PORT);

    // ── I²C + MPU-6050 init ─────────────────────────────────────────────────
    Wire.begin();
    Wire.setClock(400000);      // 400 kHz fast mode

    Serial.print("Initializing MPU-6050... ");
    mpu.initialize();
    pinMode(INT_PIN, INPUT);

    if (!mpu.testConnection()) {
        Serial.println("FAILED — check wiring!");
        blinkError();
    }
    Serial.println("OK");

    // ── DMP init ─────────────────────────────────────────────────────────────
    Serial.print("Initializing DMP... ");
    devStatus = mpu.dmpInitialize();

    // Set your own calibration offsets here (run MPU6050_calibration sketch first)
    // Leave at 0 to use the DMP's built-in auto-calibration below
    mpu.setXAccelOffset(0);
    mpu.setYAccelOffset(0);
    mpu.setZAccelOffset(0);
    mpu.setXGyroOffset(0);
    mpu.setYGyroOffset(0);
    mpu.setZGyroOffset(0);

    if (devStatus != 0) {
        Serial.printf("FAILED (code %d)\n", devStatus);
        blinkError();
    }

    // Auto-calibrate: 6 iterations each ≈ 1 second
    Serial.println("Running auto-calibration (keep sensor still)...");
    mpu.CalibrateAccel(6);
    mpu.CalibrateGyro(6);
    mpu.PrintActiveOffsets();

    mpu.setDMPEnabled(true);
    attachInterrupt(digitalPinToInterrupt(INT_PIN), dmpDataReady, RISING);
    packetSize = mpu.dmpGetFIFOPacketSize();
    dmpReady   = true;
    Serial.printf("DMP ready. Packet size: %d bytes\n", packetSize);

    // ── WiFi ────────────────────────────────────────────────────────────────
    Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\nWiFi FAILED — check credentials!");
        blinkError();
    }
    Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());
    udp.begin(6970);    // local receive port (unused, needed for WiFiUdp)

    digitalWrite(LED_PIN, HIGH);   // solid ON = ready
    Serial.println("Streaming...\n");
}

// ── Main loop ─────────────────────────────────────────────────────────────────
void loop() {
    if (!dmpReady) return;

    // Wait for DMP interrupt or extra packet
    if (!mpuInterrupt && mpu.getFIFOCount() < packetSize) return;
    mpuInterrupt = false;

    if (!mpu.dmpGetCurrentFIFOPacket(fifoBuffer)) return;

    // Extract data
    mpu.dmpGetQuaternion(&q, fifoBuffer);
    mpu.dmpGetAccel(&aa, fifoBuffer);
    mpu.dmpGetGravity(&gravity, &q);
    mpu.dmpGetLinearAccel(&aaReal, &aa, &gravity);
    mpu.dmpGetGyro(&gg, fifoBuffer);

    // Convert to physical units
    // Accel: raw / 8192 for ±4g range → g
    float ax = aaReal.x / 8192.0f;
    float ay = aaReal.y / 8192.0f;
    float az = aaReal.z / 8192.0f;
    // Gyro: raw / 131 for ±250 deg/s range → deg/s
    float gx = gg.x / 131.0f;
    float gy = gg.y / 131.0f;
    float gz = gg.z / 131.0f;

    // Pack and send
    IMUPacket pkt;
    pkt.magic_h   = MAGIC_H;
    pkt.magic_l   = MAGIC_L;
    pkt.sensor_id = SENSOR_ID;
    pkt.ptype     = PTYPE_IMU;
    pkt.qw = q.w;  pkt.qx = q.x;  pkt.qy = q.y;  pkt.qz = q.z;
    pkt.ax = ax;   pkt.ay = ay;   pkt.az = az;
    pkt.gx = gx;   pkt.gy = gy;   pkt.gz = gz;
    pkt.ts_ms = millis();

    udp.beginPacket(SERVER_IP, SERVER_PORT);
    udp.write((const uint8_t*)&pkt, sizeof(IMUPacket));
    udp.endPacket();

    // Blink LED on each packet (toggle every 50 packets ≈ 2Hz)
    static uint32_t pktCount = 0;
    if ((++pktCount % 50) == 0) {
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
void blinkError() {
    // Fast blink forever — something went wrong
    while (true) {
        digitalWrite(LED_PIN, HIGH); delay(100);
        digitalWrite(LED_PIN, LOW);  delay(100);
    }
}
