"""Tests for /api/status endpoint."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestStatusEndpoint:
    """Tests for GET /api/status."""

    @pytest.fixture
    def mock_status_data(self):
        """Sample status.json data."""
        now = datetime.now(timezone.utc)
        return {
            "sensors": {
                "interior_temp": 68.5,
                "interior_humidity": 72.3,
                "exterior_temp": 45.2,
                "exterior_humidity": 85.0,
                "satellite_battery": 3.92,
                "satellite_pressure": 30.12,
            },
            "last_seen": {
                "interior_temp": now.isoformat(),
                "interior_humidity": now.isoformat(),
                "exterior_temp": (now - timedelta(hours=3)).isoformat(),  # Stale
                "exterior_humidity": (now - timedelta(hours=3)).isoformat(),  # Stale
                "satellite_battery": now.isoformat(),
            },
            "updated_at": now.isoformat(),
        }

    @pytest.mark.unit
    def test_status_returns_sensor_values(self, mock_status_data):
        """Should return sensor values from status.json."""
        with patch("web.api.routers.status.atomic_read_json", return_value=mock_status_data):
            from web.api.routers.status import get_status
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_status())
            
            assert result["sensors"]["interior_temp"] == 68.5
            assert result["sensors"]["exterior_temp"] == 45.2

    @pytest.mark.unit
    def test_status_detects_stale_data(self, mock_status_data):
        """Should flag sensors as stale when older than threshold."""
        with patch("web.api.routers.status.atomic_read_json", return_value=mock_status_data):
            from web.api.routers.status import get_status
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_status())
            
            # Interior should be fresh
            assert result["stale"]["interior_temp"] is False
            # Exterior should be stale (3 hours old > 2 hour threshold)
            assert result["stale"]["exterior_temp"] is True

    @pytest.mark.unit
    def test_status_handles_missing_file(self):
        """Should return empty data gracefully if status.json missing."""
        with patch("web.api.routers.status.atomic_read_json", return_value={}):
            from web.api.routers.status import get_status
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_status())
            
            assert "sensors" in result
            assert "stale" in result

    @pytest.mark.unit
    def test_status_rounds_floats(self, mock_status_data):
        """Should round float values to 1 decimal place."""
        mock_status_data["sensors"]["interior_temp"] = 68.5678
        
        with patch("web.api.routers.status.atomic_read_json", return_value=mock_status_data):
            from web.api.routers.status import get_status
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_status())
            
            assert result["sensors"]["interior_temp"] == 68.6


class TestStalenessDetection:
    """Tests for check_staleness function."""

    @pytest.mark.unit
    def test_missing_timestamp_is_stale(self):
        """Missing timestamp should be considered stale."""
        from web.api.routers.status import check_staleness
        
        assert check_staleness({}, "interior_temp") is True

    @pytest.mark.unit
    def test_recent_timestamp_is_fresh(self):
        """Recent timestamp should not be stale."""
        from web.api.routers.status import check_staleness
        
        now = datetime.now(timezone.utc).isoformat()
        assert check_staleness({"interior_temp": now}, "interior_temp") is False

    @pytest.mark.unit
    def test_old_timestamp_is_stale(self):
        """Timestamp older than threshold should be stale."""
        from web.api.routers.status import check_staleness
        
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        assert check_staleness({"interior_temp": old}, "interior_temp") is True

    @pytest.mark.unit
    def test_invalid_timestamp_is_stale(self):
        """Invalid timestamp format should be considered stale."""
        from web.api.routers.status import check_staleness
        
        assert check_staleness({"interior_temp": "not-a-date"}, "interior_temp") is True
