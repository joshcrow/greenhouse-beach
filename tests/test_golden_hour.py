"""
Unit tests for golden_hour.py
"""

import pytest
from datetime import datetime
from unittest.mock import patch
from freezegun import freeze_time

import golden_hour


class TestSeasonalGoldenHour:
    """Tests for get_seasonal_golden_hour() function."""

    @pytest.mark.unit
    @freeze_time("2025-01-15")
    def test_january(self):
        """January should return 16:00."""
        assert golden_hour.get_seasonal_golden_hour() == "16:00"

    @pytest.mark.unit
    @freeze_time("2025-06-15")
    def test_june(self):
        """June (longest days) should return 19:30."""
        assert golden_hour.get_seasonal_golden_hour() == "19:30"

    @pytest.mark.unit
    @freeze_time("2025-12-15")
    def test_december(self):
        """December (shortest days) should return 15:45."""
        assert golden_hour.get_seasonal_golden_hour() == "15:45"

    @pytest.mark.unit
    def test_all_months_have_values(self):
        """All 12 months should have defined values."""
        for month in range(1, 13):
            assert month in golden_hour.SEASONAL_GOLDEN_HOURS
            time_str = golden_hour.SEASONAL_GOLDEN_HOURS[month]
            # Validate format HH:MM
            assert len(time_str) == 5
            assert time_str[2] == ":"


class TestShouldCaptureNow:
    """Tests for should_capture_now() function."""

    @pytest.mark.unit
    @freeze_time("2025-01-15 16:00:00")
    def test_exact_golden_hour(self):
        """Should return True at exact golden hour."""
        with patch("golden_hour.get_golden_hour") as mock:
            mock.return_value = datetime(2025, 1, 15, 16, 0, 0)
            assert golden_hour.should_capture_now() is True

    @pytest.mark.unit
    @freeze_time("2025-01-15 16:15:00")
    def test_within_tolerance(self):
        """Should return True within tolerance window."""
        with patch("golden_hour.get_golden_hour") as mock:
            mock.return_value = datetime(2025, 1, 15, 16, 0, 0)
            assert golden_hour.should_capture_now(tolerance_minutes=30) is True

    @pytest.mark.unit
    @freeze_time("2025-01-15 18:00:00")
    def test_outside_tolerance(self):
        """Should return False outside tolerance window."""
        with patch("golden_hour.get_golden_hour") as mock:
            mock.return_value = datetime(2025, 1, 15, 16, 0, 0)
            assert golden_hour.should_capture_now(tolerance_minutes=30) is False

    @pytest.mark.unit
    def test_no_sunset_data(self):
        """Should return False if sunset data unavailable."""
        with patch("golden_hour.get_golden_hour", return_value=None):
            assert golden_hour.should_capture_now() is False


class TestGetGoldenHour:
    """Tests for get_golden_hour() function."""

    @pytest.mark.unit
    def test_returns_one_hour_before_sunset(self):
        """Should return 1 hour before sunset."""
        sunset = datetime(2025, 6, 15, 20, 30, 0)
        with patch("golden_hour.get_sunset_time", return_value=sunset):
            result = golden_hour.get_golden_hour()
            assert result == datetime(2025, 6, 15, 19, 30, 0)

    @pytest.mark.unit
    def test_returns_none_if_no_sunset(self):
        """Should return None if sunset unavailable."""
        with patch("golden_hour.get_sunset_time", return_value=None):
            assert golden_hour.get_golden_hour() is None
