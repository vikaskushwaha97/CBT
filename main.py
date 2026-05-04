"""
main.py — Camera-Based Full Body Tracker
=========================================
Entry point for the FBT system. Starts the FastAPI dashboard server
and opens the browser automatically.

Usage
-----
    python main.py
    python main.py --camera 1 --height 177.8 --port 8765
    python main.py --osc --osc-ip 192.168.1.100 --osc-port 9000
"""

import argparse
import logging
import sys
import webbrowser
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(
        description="Camera-Based Full Body Tracker — SlimeVR-style FBT with webcam",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Default settings
  python main.py --camera 1               # Use second camera
  python main.py --height 177.8           # Set your height (cm)
  python main.py --osc --osc-ip 127.0.0.1 # Enable VRChat OSC output
  python main.py --poses 1                # Single-person mode
        """,
    )

    # Camera
    parser.add_argument("--camera", type=int, default=None, help="Camera device index (default: 0)")

    # User
    parser.add_argument("--height", type=float, default=None, help="Your height in cm (default: 177.8)")

    # Server
    parser.add_argument("--port", type=int, default=None, help="Dashboard port (default: 8765)")

    # OSC
    parser.add_argument("--osc", action="store_true", help="Enable OSC output")
    parser.add_argument("--no-osc", action="store_true", help="Disable OSC output")
    parser.add_argument("--osc-ip", type=str, default=None, help="OSC target IP (default: 127.0.0.1)")
    parser.add_argument("--osc-port", type=int, default=None, help="OSC target port (default: 9000)")

    # Detection
    parser.add_argument("--poses", type=int, default=None, help="Max persons to track (default: 5)")

    # IMU sensors
    parser.add_argument("--imu", action="store_true", help="Enable IMU sensor fusion (ESP32 + MPU-6050)")
    parser.add_argument("--imu-port", type=int, default=None, help="UDP port to listen for IMU packets (default: 6969)")
    parser.add_argument("--imu-count", type=int, default=None, help="Expected number of IMU sensors (default: 3)")

    args = parser.parse_args()

    # Build config
    from src.config import AppConfig
    config = AppConfig.from_args(args)

    # Validate
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)

    # Print startup info
    logger.info("═" * 60)
    logger.info("  Camera-Based Full Body Tracker")
    logger.info("═" * 60)
    logger.info("  Camera:     %d", config.camera_index)
    logger.info("  Resolution: %dx%d @ %d FPS", config.frame_width, config.frame_height, config.target_fps)
    logger.info("  Max Poses:  %d", config.num_poses)
    logger.info("  Height:     %.1f cm", config.user_height_cm)
    logger.info("  OSC:        %s → %s:%d", "ON" if config.osc_enabled else "OFF", config.osc_ip, config.osc_port)
    logger.info("  IMU:        %s (port %d, %d sensors)",
                "ON" if config.imu_enabled else "OFF", config.imu_port, config.imu_sensor_count)
    logger.info("  Mode:       %s", config.source_mode)
    logger.info("  Dashboard:  http://localhost:%d", config.server_port)
    logger.info("═" * 60)

    # Start IMU receiver if enabled
    imu_source = None
    if config.imu_enabled:
        from src.sources.imu_source import IMUSource
        imu_source = IMUSource(config)
        if not imu_source.start():
            logger.error("Failed to start IMU receiver on port %d. Continuing in camera-only mode.",
                         config.imu_port)
            imu_source = None
        else:
            logger.info("IMU receiver ready on UDP :%d — waiting for sensor connections...",
                        config.imu_port)

    # Auto-open browser after short delay
    def open_browser():
        import time
        time.sleep(2.0)
        webbrowser.open(f"http://localhost:{config.server_port}")

    threading.Thread(target=open_browser, daemon=True).start()

    # Start server (blocking)
    from src.server import run_server
    run_server(config, imu_source=imu_source)


if __name__ == "__main__":
    main()
