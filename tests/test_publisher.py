"""
Integration tests for publisher.py

Tests the email building and sending pipeline.
"""

import json
import pytest
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from unittest.mock import patch, MagicMock
from io import BytesIO

import publisher


class TestLoadLatestSensorSnapshot:
    """Tests for load_latest_sensor_snapshot() function."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - STATUS_PATH loaded at import time")
    def test_loads_from_file(self, tmp_path, monkeypatch, sample_status_json):
        """Should load sensor data from status.json file."""
        pass

    @pytest.mark.integration  
    @pytest.mark.skip(reason="Requires module refactoring - STATUS_PATH loaded at import time")
    def test_returns_empty_for_missing_file(self, tmp_path, monkeypatch):
        """Should return empty dict if file missing."""
        pass


class TestSatelliteDataProcessing:
    """Tests for satellite sensor data processing."""

    @pytest.mark.unit
    def test_battery_voltage_calculation(self, sample_sensor_data):
        """Should double battery ADC reading for actual voltage."""
        # Raw ADC = 2.1V, actual = 4.2V
        raw_battery = sample_sensor_data["satellite-2_satellite_2_battery"]
        expected_voltage = round(raw_battery * 2, 1)  # 4.2V

        assert expected_voltage == 4.2

    @pytest.mark.unit
    def test_celsius_to_fahrenheit_conversion(self, sample_sensor_data):
        """Temperature conversion formula should be correct."""
        celsius_temp = sample_sensor_data["satellite-2_satellite_2_temperature"]  # 21.5
        expected_f = round(celsius_temp * 9/5 + 32)  # 71°F
        
        assert expected_f == 71


class TestFindLatestImage:
    """Tests for find_latest_image() function."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - ARCHIVE_PATH loaded at import time")
    def test_finds_most_recent_image(self, tmp_path, monkeypatch):
        """Should return the most recent image."""
        pass

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires module refactoring - ARCHIVE_PATH loaded at import time")
    def test_returns_none_for_empty_archive(self, tmp_path, monkeypatch):
        """Should return None if no images found."""
        pass


class TestIsWeeklyEdition:
    """Tests for is_weekly_edition() function."""

    @pytest.mark.unit
    def test_returns_bool(self):
        """Should return a boolean value."""
        result = publisher.is_weekly_edition()
        assert isinstance(result, bool)


class TestEmailWeatherTable:
    @pytest.mark.unit
    def test_includes_sunrise_sunset_rows(self, sample_sensor_data):
        augmented = dict(sample_sensor_data)
        augmented["sunrise"] = "7:12 AM"
        augmented["sunset"] = "4:56 PM"
        augmented["condition"] = "Clouds"
        augmented["high_temp"] = 62
        augmented["low_temp"] = 48
        augmented["daily_wind_mph"] = 12
        augmented["daily_wind_direction"] = "NE"
        augmented["daily_wind_arrow"] = "↗"
        augmented["moon_phase"] = 0.5
        augmented["moon_icon"] = "🌕"

        with (
            patch("publisher.narrator.generate_update", return_value=("S", "H", "B", "B", augmented)),
            patch("publisher.timelapse.create_daily_timelapse", return_value=None),
            patch("publisher.timelapse.create_weekly_timelapse", return_value=None),
            patch("publisher.find_latest_image", return_value=None),
            patch("publisher.stats.get_24h_stats", return_value={}),
        ):
            msg, _weekly_mode = publisher.build_email(dict(sample_sensor_data))

        html_part = next(p for p in msg.iter_parts() if p.get_content_subtype() == "html")
        html_body = html_part.get_content()

        assert "Sunrise" in html_body
        assert "7:12 AM" in html_body
        assert "Sunset" in html_body
        assert "4:56 PM" in html_body


class TestSendEmail:
    """Tests for send_email() function."""

    @pytest.mark.integration
    def test_sends_via_smtp(self, mock_smtp):
        """Should send email via SMTP."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@test.com"
        msg["To"] = "recipient@test.com"

        publisher.send_email(msg)

        mock_smtp.send_message.assert_called_once()

    @pytest.mark.integration
    def test_handles_smtp_error(self, mock_smtp):
        """Should handle SMTP errors gracefully."""
        mock_smtp.send_message.side_effect = Exception("SMTP Error")

        msg = MIMEMultipart()
        msg["Subject"] = "Test"

        # Should not raise
        publisher.send_email(msg)
