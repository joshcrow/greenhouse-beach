"""
Unit tests for status_daemon.py
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import status_daemon


class TestParsePayload:
    """Tests for _parse_payload() function."""

    @pytest.mark.unit
    def test_parses_float(self):
        """Should parse numeric payload as float."""
        result = status_daemon._parse_payload(b"72.5")
        assert result == 72.5

    @pytest.mark.unit
    def test_parses_integer(self):
        """Should parse integer payload as float."""
        result = status_daemon._parse_payload(b"100")
        assert result == 100.0

    @pytest.mark.unit
    def test_returns_string_for_non_numeric(self):
        """Should return string for non-numeric payload."""
        result = status_daemon._parse_payload(b"clear")
        assert result == "clear"

    @pytest.mark.unit
    def test_strips_whitespace(self):
        """Should strip whitespace from payload."""
        result = status_daemon._parse_payload(b"  72.5  \n")
        assert result == 72.5


class TestKeyFromTopic:
    """Tests for _key_from_topic() function."""

    @pytest.mark.unit
    def test_extracts_device_and_sensor(self):
        """Should extract device and sensor from topic."""
        topic = "greenhouse/interior/sensor/temp/state"
        result = status_daemon._key_from_topic(topic)
        assert result == "interior_temp"

    @pytest.mark.unit
    def test_handles_complex_device_names(self):
        """Should handle device names with hyphens."""
        topic = "greenhouse/satellite-2/sensor/temperature/state"
        result = status_daemon._key_from_topic(topic)
        assert result == "satellite-2_temperature"

    @pytest.mark.unit
    def test_returns_none_for_invalid_topic(self):
        """Should return None for malformed topic."""
        invalid_topics = [
            "greenhouse/device",
            "greenhouse",
            "",
            "not/a/greenhouse/topic",
        ]
        for topic in invalid_topics:
            result = status_daemon._key_from_topic(topic)
            assert result is None, f"Topic '{topic}' should return None"


class TestValidationAndSpikes:
    @pytest.mark.unit
    def test_validate_numeric_converts_satellite_temp_to_f(self):
        ok, v = status_daemon._validate_numeric("satellite-2", "satellite_2_temperature", 21.0)
        assert ok is True
        assert round(v, 1) == 69.8

    @pytest.mark.unit
    def test_validate_numeric_rejects_out_of_range_temp(self):
        ok, _ = status_daemon._validate_numeric("interior", "temp", 500.0)
        assert ok is False

    @pytest.mark.unit
    def test_is_spike_detects_temp_spike(self):
        now = datetime.utcnow()
        key = "interior_temp"
        status_daemon.last_seen[key] = now - timedelta(seconds=30)
        status_daemon.last_numeric_value[key] = 70.0
        try:
            assert status_daemon._is_spike(key, now, 100.0, "temp") is True
        finally:
            status_daemon.last_seen.clear()
            status_daemon.last_numeric_value.clear()


class TestPruneAndComputeStats:
    """Tests for _prune_and_compute_stats() function."""

    @pytest.mark.unit
    def test_computes_min_max(self):
        """Should compute min and max for numeric values."""
        now = datetime.utcnow()
        status_daemon.history["temp"] = [
            (now - timedelta(hours=1), 65.0),
            (now - timedelta(hours=2), 70.0),
            (now - timedelta(hours=3), 75.0),
        ]

        try:
            metrics = status_daemon._prune_and_compute_stats(now)
            assert metrics["temp_min"] == 65.0
            assert metrics["temp_max"] == 75.0
        finally:
            status_daemon.history.clear()

    @pytest.mark.unit
    def test_prunes_old_data(self):
        """Should remove data older than 24 hours."""
        now = datetime.utcnow()
        status_daemon.history["temp"] = [
            (now - timedelta(hours=30), 50.0),  # Old - should be pruned
            (now - timedelta(hours=1), 70.0),   # Recent - should stay
        ]

        try:
            status_daemon._prune_and_compute_stats(now)
            assert len(status_daemon.history["temp"]) == 1
            assert status_daemon.history["temp"][0][1] == 70.0
        finally:
            status_daemon.history.clear()

    @pytest.mark.unit
    def test_ignores_non_numeric_history(self):
        """Should skip non-numeric values in history."""
        now = datetime.utcnow()
        status_daemon.history["condition"] = [
            (now - timedelta(hours=1), "clear"),
            (now - timedelta(hours=2), "cloudy"),
        ]

        try:
            metrics = status_daemon._prune_and_compute_stats(now)
            assert "condition_min" not in metrics
            assert "condition_max" not in metrics
        finally:
            status_daemon.history.clear()

    @pytest.mark.unit
    def test_handles_empty_history(self):
        """Should return empty metrics for empty history."""
        status_daemon.history.clear()
        metrics = status_daemon._prune_and_compute_stats(datetime.utcnow())
        assert metrics == {}


class TestHistoryCache:
    """Tests for history persistence functions."""

    @pytest.mark.unit
    def test_save_and_load_cache(self, tmp_path, monkeypatch):
        """Should save and restore history cache."""
        cache_path = tmp_path / "history_cache.json"
        monkeypatch.setenv("HISTORY_CACHE_PATH", str(cache_path))
        
        # Reload module to pick up new env var
        import importlib
        importlib.reload(status_daemon)

        now = datetime.utcnow()
        status_daemon.history["temp"] = [(now, 72.0)]
        status_daemon.latest_values["temp"] = 72.0
        status_daemon.last_seen["temp"] = now

        try:
            # Save cache
            status_daemon._save_history_cache()
            assert cache_path.exists()

            # Clear and reload
            status_daemon.history.clear()
            status_daemon.latest_values.clear()
            status_daemon.last_seen.clear()
            status_daemon._load_history_cache()

            # Verify restored (within 24h window)
            assert "temp" in status_daemon.latest_values
            assert "temp" in status_daemon.last_seen
        finally:
            status_daemon.history.clear()
            status_daemon.latest_values.clear()
            status_daemon.last_seen.clear()

    @pytest.mark.unit
    def test_load_handles_missing_file(self, tmp_path, monkeypatch):
        """Should handle missing cache file gracefully."""
        monkeypatch.setenv("HISTORY_CACHE_PATH", str(tmp_path / "nonexistent.json"))
        
        import importlib
        importlib.reload(status_daemon)

        # Should not raise
        status_daemon._load_history_cache()


class TestStatusSnapshot:
    @pytest.mark.unit
    def test_status_snapshot_includes_last_seen(self, tmp_path, monkeypatch):
        status_path = tmp_path / "status.json"
        stats_path = tmp_path / "stats_24h.json"
        cache_path = tmp_path / "history_cache.json"
        monkeypatch.setenv("STATUS_PATH", str(status_path))
        monkeypatch.setenv("STATS_24H_PATH", str(stats_path))
        monkeypatch.setenv("HISTORY_CACHE_PATH", str(cache_path))
        monkeypatch.setenv("STATUS_WRITE_INTERVAL", "0")

        import importlib
        importlib.reload(status_daemon)

        now = datetime.utcnow()
        status_daemon.latest_values["interior_temp"] = 70.0
        status_daemon.last_seen["interior_temp"] = now

        try:
            status_daemon._write_files_if_due(now)
            payload = json.loads(status_path.read_text())
            assert "last_seen" in payload
            assert "interior_temp" in payload["last_seen"]
        finally:
            status_daemon.latest_values.clear()
            status_daemon.history.clear()
            status_daemon.last_seen.clear()
