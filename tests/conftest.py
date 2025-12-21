"""
Pytest configuration and shared fixtures for Greenhouse Gazette tests.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set default environment variables for all tests."""
    env_defaults = {
        "MQTT_HOST": "localhost",
        "MQTT_PORT": "1883",
        "MQTT_USERNAME": "test_user",
        "MQTT_PASSWORD": "test_pass",
        "GEMINI_API_KEY": "test-gemini-key",
        "GEMINI_MODEL": "gemini-2.5-flash",
        "OPENWEATHER_API_KEY": "test-weather-key",
        "LAT": "36.022",
        "LON": "-75.720",
        "SMTP_SERVER": "smtp.test.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "test@test.com",
        "SMTP_PASSWORD": "test-smtp-pass",
        "SMTP_FROM": "Greenhouse <test@test.com>",
        "SMTP_TO": "recipient@test.com",
        "STATUS_PATH": "/tmp/test_status.json",
        "STATS_24H_PATH": "/tmp/test_stats_24h.json",
        "TZ": "America/New_York",
    }
    for key, value in env_defaults.items():
        monkeypatch.setenv(key, value)


# =============================================================================
# Data Fixtures
# =============================================================================

@pytest.fixture
def sample_sensor_data() -> Dict[str, Any]:
    """Sample sensor data matching production format."""
    return {
        "interior_temp": 72,
        "interior_humidity": 65,
        "exterior_temp": 58,
        "exterior_humidity": 78,
        "satellite-2_satellite_2_temperature": 21.5,  # Celsius
        "satellite-2_satellite_2_humidity": 82,
        "satellite-2_satellite_2_battery": 2.1,  # ADC reading (actual = 4.2V)
    }


@pytest.fixture
def sample_weather_data() -> Dict[str, Any]:
    """Sample weather API response data."""
    return {
        "outdoor_temp": 55,
        "humidity_out": 70,
        "condition": "Clouds",
        "high_temp": 62,
        "low_temp": 48,
        "sunrise": "7:12 AM",
        "sunset": "4:56 PM",
        "wind_mph": 12,
        "wind_direction": "NE",
        "wind_arrow": "↗",
        "moon_phase": 0.5,
        "moon_icon": "🌕",
    }


@pytest.fixture
def sample_stats_24h() -> Dict[str, Any]:
    """Sample 24-hour statistics data."""
    now = datetime.utcnow()
    return {
        "window_start": (now - timedelta(hours=24)).isoformat() + "Z",
        "window_end": now.isoformat() + "Z",
        "metrics": {
            "interior_temp_min": 65,
            "interior_temp_max": 78,
            "interior_humidity_min": 55,
            "interior_humidity_max": 72,
            "satellite-2_satellite_2_temperature_min": 18.0,
            "satellite-2_satellite_2_temperature_max": 25.0,
            "satellite-2_satellite_2_humidity_min": 75,
            "satellite-2_satellite_2_humidity_max": 88,
        },
    }


@pytest.fixture
def sample_status_json(sample_sensor_data) -> Dict[str, Any]:
    """Sample status.json content."""
    return {
        "sensors": sample_sensor_data,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


# =============================================================================
# File System Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory structure."""
    data_dir = tmp_path / "data"
    (data_dir / "incoming").mkdir(parents=True)
    (data_dir / "archive").mkdir(parents=True)
    return data_dir


@pytest.fixture
def temp_status_file(tmp_path, sample_status_json):
    """Create a temporary status.json file."""
    status_path = tmp_path / "status.json"
    with open(status_path, "w") as f:
        json.dump(sample_status_json, f)
    return status_path


@pytest.fixture
def temp_stats_file(tmp_path, sample_stats_24h):
    """Create a temporary stats_24h.json file."""
    stats_path = tmp_path / "stats_24h.json"
    with open(stats_path, "w") as f:
        json.dump(sample_stats_24h, f)
    return stats_path


@pytest.fixture
def sample_image_bytes():
    """Generate minimal valid JPEG bytes for testing."""
    # Minimal valid JPEG (1x1 pixel red)
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xBA, 0xAE, 0xEB,
        0xB8, 0x6D, 0x38, 0x4C, 0x8A, 0x28, 0xA0, 0x02, 0x8A, 0x28, 0x03, 0xFF,
        0xD9
    ])


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_mqtt_client():
    """Mock paho MQTT client."""
    with patch("paho.mqtt.client.Client") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_instance.connect.return_value = 0
        mock_instance.publish.return_value = MagicMock(is_published=lambda: True)
        yield mock_instance


@pytest.fixture
def mock_gemini():
    """Mock Google Generative AI (new google-genai SDK)."""
    with patch("narrator.genai") as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        
        # Mock response structure for new SDK
        mock_response = MagicMock()
        mock_response.text = """SUBJECT: Perfect Growing Conditions Today

HEADLINE: Mild temps and gentle breeze keep plants happy

BODY: The greenhouse is thriving today with temperatures in the comfortable range. 
Humidity levels are ideal for most plants.

Expect similar conditions through the afternoon. No action needed."""
        mock_client.models.generate_content.return_value = mock_response
        yield mock_client


@pytest.fixture
def mock_smtp():
    """Mock SMTP connection."""
    with patch("smtplib.SMTP_SSL") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_class.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_instance
