"""
Unit tests for narrator.py
"""

import pytest
from unittest.mock import patch, MagicMock

import narrator


class TestSanitizeData:
    """Tests for sanitize_data() function."""

    @pytest.mark.unit
    def test_valid_data_unchanged(self):
        """Valid data within bounds should pass through."""
        data = {
            "interior_temp": 72,
            "interior_humidity": 65,
            "exterior_temp": 58,
        }
        result = narrator.sanitize_data(data)
        
        assert result["interior_temp"] == 72
        assert result["interior_humidity"] == 65
        assert result["exterior_temp"] == 58

    @pytest.mark.unit
    def test_temp_below_minimum_nullified(self):
        """Temperature below -10°F should be nullified."""
        data = {"interior_temp": -20}
        result = narrator.sanitize_data(data)
        assert result["interior_temp"] is None

    @pytest.mark.unit
    def test_temp_above_maximum_nullified(self):
        """Temperature above 130°F should be nullified."""
        data = {"interior_temp": 150}
        result = narrator.sanitize_data(data)
        assert result["interior_temp"] is None

    @pytest.mark.unit
    def test_temp_at_boundaries_valid(self):
        """Temperature at exact boundaries should be valid."""
        data_low = {"interior_temp": -10}
        data_high = {"interior_temp": 130}
        
        assert narrator.sanitize_data(data_low)["interior_temp"] == -10
        assert narrator.sanitize_data(data_high)["interior_temp"] == 130

    @pytest.mark.unit
    def test_humidity_below_zero_nullified(self):
        """Humidity below 0% should be nullified."""
        data = {"interior_humidity": -5}
        result = narrator.sanitize_data(data)
        assert result["interior_humidity"] is None

    @pytest.mark.unit
    def test_humidity_above_100_nullified(self):
        """Humidity above 100% should be nullified."""
        data = {"interior_humidity": 110}
        result = narrator.sanitize_data(data)
        assert result["interior_humidity"] is None

    @pytest.mark.unit
    def test_humidity_at_boundaries_valid(self):
        """Humidity at exact boundaries should be valid."""
        data_low = {"interior_humidity": 0}
        data_high = {"interior_humidity": 100}
        
        assert narrator.sanitize_data(data_low)["interior_humidity"] == 0
        assert narrator.sanitize_data(data_high)["interior_humidity"] == 100

    @pytest.mark.unit
    def test_non_numeric_temp_nullified(self):
        """Non-numeric temperature should be nullified."""
        data = {"interior_temp": "warm"}
        result = narrator.sanitize_data(data)
        assert result["interior_temp"] is None

    @pytest.mark.unit
    def test_non_numeric_humidity_nullified(self):
        """Non-numeric humidity should be nullified."""
        data = {"interior_humidity": "high"}
        result = narrator.sanitize_data(data)
        assert result["interior_humidity"] is None

    @pytest.mark.unit
    def test_all_temp_keys_sanitized(self):
        """All temperature key variants should be sanitized."""
        temp_keys = [
            "temp", "interior_temp", "exterior_temp", "outdoor_temp",
            "satellite_2_temperature", "satellite-2_satellite_2_temperature",
            "high_temp", "low_temp",
        ]
        
        for key in temp_keys:
            data = {key: 200}  # Invalid
            result = narrator.sanitize_data(data)
            assert result[key] is None, f"Key {key} was not sanitized"

    @pytest.mark.unit
    def test_all_humidity_keys_sanitized(self):
        """All humidity key variants should be sanitized."""
        humidity_keys = [
            "humidity", "interior_humidity", "exterior_humidity", "humidity_out",
            "satellite_2_humidity", "satellite-2_satellite_2_humidity",
        ]
        
        for key in humidity_keys:
            data = {key: 150}  # Invalid
            result = narrator.sanitize_data(data)
            assert result[key] is None, f"Key {key} was not sanitized"

    @pytest.mark.unit
    def test_none_values_preserved(self):
        """None values should remain None."""
        data = {"interior_temp": None}
        result = narrator.sanitize_data(data)
        assert result["interior_temp"] is None

    @pytest.mark.unit
    def test_unrelated_keys_preserved(self):
        """Keys not in sanitization list should be preserved."""
        data = {
            "condition": "Sunny",
            "wind_mph": 15,
            "custom_field": "test",
        }
        result = narrator.sanitize_data(data)
        
        assert result["condition"] == "Sunny"
        assert result["wind_mph"] == 15
        assert result["custom_field"] == "test"


class TestBuildPrompt:
    """Tests for build_prompt() function."""

    @pytest.mark.unit
    def test_prompt_contains_data(self):
        """Prompt should contain the sensor data."""
        data = {"interior_temp": 72, "humidity": 65}
        prompt = narrator.build_prompt(data)
        
        assert "72" in prompt
        assert "65" in prompt

    @pytest.mark.unit
    def test_prompt_contains_rules(self):
        """Prompt should contain formatting rules."""
        prompt = narrator.build_prompt({})
        
        assert "RULES:" in prompt
        assert "SUBJECT:" in prompt
        assert "HEADLINE:" in prompt
        assert "BODY:" in prompt

    @pytest.mark.unit
    def test_prompt_mentions_alerts(self):
        """Prompt should mention alert conditions."""
        prompt = narrator.build_prompt({})
        
        assert "Freezing" in prompt or "35°F" in prompt
        assert "battery" in prompt.lower()


class TestGenerateUpdate:
    """Tests for generate_update() function."""

    @pytest.mark.unit
    def test_returns_tuple_of_five(self, mock_gemini):
        """Should return (subject, headline, body_html, body_plain, data) tuple."""
        with patch("narrator.weather_service.get_current_weather", return_value={}):
            result = narrator.generate_update({"interior_temp": 72})
        
        assert isinstance(result, tuple)
        assert len(result) == 5

    @pytest.mark.unit
    def test_parses_gemini_response(self, mock_gemini):
        """Should parse structured response from Gemini."""
        with patch("narrator.weather_service.get_current_weather", return_value={}):
            subject, headline, body_html, body_plain, data = narrator.generate_update({"interior_temp": 72})
        
        assert "Perfect Growing Conditions" in subject
        assert len(headline) > 0
        assert len(body_html) > 0
        assert len(body_plain) > 0

    @pytest.mark.unit
    def test_fallback_on_api_error(self):
        """Should return fallback values on API error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")
        with patch("narrator._get_client", return_value=mock_client):
            with patch("narrator.weather_service.get_current_weather", return_value={}):
                with patch("narrator.coast_sky_service.get_coast_sky_summary", return_value={}):
                    subject, headline, body_html, body_plain, data = narrator.generate_update({})
        
        assert subject == "Greenhouse Update"
        assert headline == "Greenhouse Update"
        assert "error" in body_html.lower() or "error" in body_plain.lower()

    @pytest.mark.unit
    def test_weather_data_merged(self, mock_gemini):
        """Should merge weather data into sensor data."""
        weather = {"outdoor_temp": 55, "condition": "Clear"}
        
        with patch("narrator.weather_service.get_current_weather", return_value=weather):
            _, _, _, _, augmented_data = narrator.generate_update({"interior_temp": 72})
        
        assert augmented_data.get("condition") == "Clear"
