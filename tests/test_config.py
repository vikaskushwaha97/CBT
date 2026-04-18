"""Tests for configuration system."""

import os
import pytest
from src.config import AppConfig


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.camera_index == 0
        assert config.frame_width == 640
        assert config.frame_height == 480
        assert config.target_fps == 30
        assert config.num_poses == 5
        assert config.user_height_cm == 177.8
        assert config.osc_port == 9000
        assert config.server_port == 8765

    def test_validation_valid(self):
        config = AppConfig()
        errors = config.validate()
        assert errors == []

    def test_validation_bad_height(self):
        config = AppConfig()
        config.user_height_cm = 50  # too short
        errors = config.validate()
        assert any("height" in e for e in errors)

    def test_validation_bad_resolution(self):
        config = AppConfig()
        config.frame_width = 100  # too small
        errors = config.validate()
        assert any("frame_width" in e for e in errors)

    def test_validation_bad_poses(self):
        config = AppConfig()
        config.num_poses = 0
        errors = config.validate()
        assert any("num_poses" in e for e in errors)

    def test_from_args_camera(self):
        class Args:
            camera = 2
            height = None
            osc_ip = None
            osc_port = None
            no_osc = False
            osc = False
            poses = None
            port = None

        config = AppConfig.from_args(Args())
        assert config.camera_index == 2

    def test_from_args_height(self):
        class Args:
            camera = None
            height = 180.0
            osc_ip = None
            osc_port = None
            no_osc = False
            osc = False
            poses = None
            port = None

        config = AppConfig.from_args(Args())
        assert config.user_height_cm == 180.0
