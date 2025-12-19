"""
Unit tests for stats.py
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

import stats


class TestLoadStatsFile:
    """Tests for _load_stats_file() function."""

    @pytest.mark.unit
    def test_loads_valid_json(self, tmp_path):
        """Should load and return valid JSON."""
        file_path = tmp_path / "stats.json"
        data = {"metrics": {"temp_min": 65}}
        file_path.write_text(json.dumps(data))

        result = stats._load_stats_file(str(file_path))
        assert result == data

    @pytest.mark.unit
    def test_returns_none_for_missing_file(self, tmp_path):
        """Should return None for non-existent file."""
        result = stats._load_stats_file(str(tmp_path / "nonexistent.json"))
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_invalid_json(self, tmp_path):
        """Should return None for invalid JSON."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("not valid json {")

        result = stats._load_stats_file(str(file_path))
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_empty_file(self, tmp_path):
        """Should return None for empty file."""
        file_path = tmp_path / "empty.json"
        file_path.write_text("")

        result = stats._load_stats_file(str(file_path))
        assert result is None


class TestGet24hStats:
    """Tests for get_24h_stats() function."""

    @pytest.mark.unit
    def test_returns_metrics_from_file(self, tmp_path, monkeypatch, sample_stats_24h):
        """Should return metrics from stats file."""
        file_path = tmp_path / "stats_24h.json"
        file_path.write_text(json.dumps(sample_stats_24h))
        monkeypatch.setenv("STATS_24H_PATH", str(file_path))

        result = stats.get_24h_stats(datetime.utcnow())

        assert result["interior_temp_min"] == 65
        assert result["interior_temp_max"] == 78

    @pytest.mark.unit
    def test_returns_empty_dict_for_missing_file(self, tmp_path, monkeypatch):
        """Should return empty dict if file missing."""
        monkeypatch.setenv("STATS_24H_PATH", str(tmp_path / "nonexistent.json"))

        result = stats.get_24h_stats(datetime.utcnow())
        assert result == {}

    @pytest.mark.unit
    @pytest.mark.skip(reason="Stale data detection not yet implemented in stats module")
    def test_returns_empty_dict_for_stale_data(self, tmp_path, monkeypatch):
        """Should return empty dict if data is older than 25 hours."""
        pass

    @pytest.mark.unit
    def test_returns_empty_dict_for_missing_metrics_key(self, tmp_path, monkeypatch):
        """Should return empty dict if metrics key missing."""
        data = {"window_end": datetime.utcnow().isoformat() + "Z"}
        file_path = tmp_path / "stats_24h.json"
        file_path.write_text(json.dumps(data))
        monkeypatch.setenv("STATS_24H_PATH", str(file_path))

        result = stats.get_24h_stats(datetime.utcnow())
        assert result == {}
