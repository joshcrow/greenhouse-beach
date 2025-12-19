"""
Unit tests for weather_service.py
"""

import pytest
import responses
from unittest.mock import patch

import weather_service


class TestWindDirection:
    """Tests for _wind_direction() function."""

    @pytest.mark.unit
    def test_north(self):
        assert weather_service._wind_direction(0) == "N"
        assert weather_service._wind_direction(360) == "N"

    @pytest.mark.unit
    def test_cardinal_directions(self):
        assert weather_service._wind_direction(45) == "NE"
        assert weather_service._wind_direction(90) == "E"
        assert weather_service._wind_direction(135) == "SE"
        assert weather_service._wind_direction(180) == "S"
        assert weather_service._wind_direction(225) == "SW"
        assert weather_service._wind_direction(270) == "W"
        assert weather_service._wind_direction(315) == "NW"

    @pytest.mark.unit
    def test_boundary_values(self):
        # Test values near boundaries
        assert weather_service._wind_direction(22) == "N"
        assert weather_service._wind_direction(23) == "NE"
        assert weather_service._wind_direction(67) == "NE"
        assert weather_service._wind_direction(68) == "E"


class TestWindArrow:
    """Tests for _wind_arrow() function."""

    @pytest.mark.unit
    def test_arrows(self):
        assert weather_service._wind_arrow(0) == "↑"
        assert weather_service._wind_arrow(45) == "↗"
        assert weather_service._wind_arrow(90) == "→"
        assert weather_service._wind_arrow(135) == "↘"
        assert weather_service._wind_arrow(180) == "↓"
        assert weather_service._wind_arrow(225) == "↙"
        assert weather_service._wind_arrow(270) == "←"
        assert weather_service._wind_arrow(315) == "↖"
        assert weather_service._wind_arrow(360) == "↑"


class TestMoonPhaseIcon:
    """Tests for _moon_phase_icon() function."""

    @pytest.mark.unit
    def test_new_moon(self):
        assert weather_service._moon_phase_icon(0) == "🌑"
        assert weather_service._moon_phase_icon(0.9) == "🌑"
        assert weather_service._moon_phase_icon(1.0) == "🌑"

    @pytest.mark.unit
    def test_all_phases(self):
        assert weather_service._moon_phase_icon(0.15) == "🌒"  # waxing crescent
        assert weather_service._moon_phase_icon(0.30) == "🌓"  # first quarter
        assert weather_service._moon_phase_icon(0.40) == "🌔"  # waxing gibbous
        assert weather_service._moon_phase_icon(0.50) == "🌕"  # full moon
        assert weather_service._moon_phase_icon(0.60) == "🌕"  # full moon
        assert weather_service._moon_phase_icon(0.65) == "🌖"  # waning gibbous
        assert weather_service._moon_phase_icon(0.75) == "🌗"  # last quarter


class TestGetCurrentWeather:
    """Tests for get_current_weather() function."""

    @pytest.mark.unit
    def test_missing_config_returns_empty(self, monkeypatch):
        """Should return empty dict if API key is missing."""
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        result = weather_service.get_current_weather()
        assert result == {}

    @pytest.mark.unit
    def test_missing_lat_returns_empty(self, monkeypatch):
        """Should return empty dict if LAT is missing."""
        monkeypatch.delenv("LAT", raising=False)
        result = weather_service.get_current_weather()
        assert result == {}

    @pytest.mark.unit
    @responses.activate
    def test_successful_api_call(self):
        """Should parse API response correctly."""
        api_response = {
            "current": {
                "temp": 72.5,
                "humidity": 65,
                "wind_speed": 12.3,
                "wind_deg": 180,
                "weather": [{"main": "Clouds"}],
            },
            "daily": [
                {
                    "temp": {"max": 78, "min": 55},
                    "moon_phase": 0.5,
                    "wind_speed": 15,
                    "wind_deg": 200,
                }
            ],
        }

        responses.add(
            responses.GET,
            "https://api.openweathermap.org/data/3.0/onecall",
            json=api_response,
            status=200,
        )

        result = weather_service.get_current_weather()

        assert result["outdoor_temp"] == 72  # Rounded
        assert result["humidity_out"] == 65
        assert result["condition"] == "Clouds"
        assert result["high_temp"] == 78
        assert result["low_temp"] == 55
        assert result["wind_mph"] == 12
        assert result["wind_direction"] == "S"
        assert result["moon_phase"] == 0.5
        assert result["moon_icon"] == "🌕"

    @pytest.mark.unit
    @responses.activate
    def test_api_error_returns_empty(self):
        """Should return empty dict on API error."""
        responses.add(
            responses.GET,
            "https://api.openweathermap.org/data/3.0/onecall",
            json={"error": "Unauthorized"},
            status=401,
        )

        result = weather_service.get_current_weather()
        assert result == {}

    @pytest.mark.unit
    @responses.activate
    def test_network_error_returns_empty(self):
        """Should return empty dict on network error."""
        responses.add(
            responses.GET,
            "https://api.openweathermap.org/data/3.0/onecall",
            body=Exception("Connection failed"),
        )

        result = weather_service.get_current_weather()
        assert result == {}
