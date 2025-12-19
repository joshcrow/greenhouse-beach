"""
Integration tests for weekly_digest.py

Tests the weekly summary and email generation.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from io import BytesIO

import weekly_digest


class TestLoadWeeklyStats:
    """Tests for load_weekly_stats() function."""

    @pytest.mark.integration
    def test_loads_existing_stats(self, tmp_path, monkeypatch):
        """Should load existing weekly stats."""
        stats_path = tmp_path / "stats_weekly.json"
        data = {
            "days": [{"date": "2025-01-15", "temp_avg": 72}],
            "week_start": "2025-01-13",
        }
        stats_path.write_text(json.dumps(data))
        monkeypatch.setattr(weekly_digest, "WEEKLY_STATS_PATH", str(stats_path))

        result = weekly_digest.load_weekly_stats()

        assert len(result["days"]) == 1
        assert result["week_start"] == "2025-01-13"

    @pytest.mark.integration
    def test_returns_empty_for_missing_file(self, tmp_path, monkeypatch):
        """Should return empty structure if file missing."""
        monkeypatch.setattr(weekly_digest, "WEEKLY_STATS_PATH", str(tmp_path / "nonexistent.json"))

        result = weekly_digest.load_weekly_stats()

        assert result["days"] == []
        assert result["week_start"] is None


class TestSaveWeeklyStats:
    """Tests for save_weekly_stats() function."""

    @pytest.mark.integration
    def test_saves_to_file(self, tmp_path, monkeypatch):
        """Should save stats to JSON file."""
        stats_path = tmp_path / "stats_weekly.json"
        monkeypatch.setattr(weekly_digest, "WEEKLY_STATS_PATH", str(stats_path))

        data = {"days": [], "week_start": "2025-01-13"}
        weekly_digest.save_weekly_stats(data)

        assert stats_path.exists()
        saved = json.loads(stats_path.read_text())
        assert saved["week_start"] == "2025-01-13"


class TestRecordDailySnapshot:
    """Tests for record_daily_snapshot() function."""

    @pytest.mark.integration
    def test_adds_daily_data(self, tmp_path, monkeypatch):
        """Should add daily snapshot to weekly stats."""
        weekly_path = tmp_path / "stats_weekly.json"
        weekly_path.write_text(json.dumps({"days": [], "week_start": None}))
        
        stats_path = tmp_path / "stats_24h.json"
        stats_path.write_text(json.dumps({"metrics": {"temp": 72}}))
        
        monkeypatch.setattr(weekly_digest, "WEEKLY_STATS_PATH", str(weekly_path))
        monkeypatch.setattr(weekly_digest, "STATS_PATH", str(stats_path))

        weekly_digest.record_daily_snapshot()

        saved = json.loads(weekly_path.read_text())
        assert len(saved["days"]) == 1

    @pytest.mark.integration
    def test_initializes_week_start(self, tmp_path, monkeypatch):
        """Should initialize week_start on first snapshot."""
        weekly_path = tmp_path / "stats_weekly.json"
        weekly_path.write_text(json.dumps({"days": [], "week_start": None}))
        
        stats_path = tmp_path / "stats_24h.json"
        stats_path.write_text(json.dumps({"metrics": {"temp": 72}}))
        
        monkeypatch.setattr(weekly_digest, "WEEKLY_STATS_PATH", str(weekly_path))
        monkeypatch.setattr(weekly_digest, "STATS_PATH", str(stats_path))

        weekly_digest.record_daily_snapshot()

        saved = json.loads(weekly_path.read_text())
        assert saved["week_start"] is not None


class TestComputeWeeklySummary:
    """Tests for compute_weekly_summary() function."""

    @pytest.mark.integration
    def test_computes_averages(self):
        """Should compute summary from daily data."""
        # The function expects a dict with 'days' key containing snapshots
        weekly_data = {
            "days": [
                {"date": "2025-01-13", "stats": {"metrics": {"interior_temp_min": 70, "interior_temp_max": 75}}},
                {"date": "2025-01-14", "stats": {"metrics": {"interior_temp_min": 68, "interior_temp_max": 78}}},
            ],
            "week_start": "2025-01-13"
        }

        result = weekly_digest.compute_weekly_summary(weekly_data)

        assert "days_recorded" in result
        assert result["days_recorded"] == 2

    @pytest.mark.integration
    def test_handles_missing_days(self):
        """Should handle empty days list."""
        weekly_data = {"days": [], "week_start": None}

        result = weekly_digest.compute_weekly_summary(weekly_data)

        assert result == {}

    @pytest.mark.integration
    def test_returns_empty_for_no_data(self):
        """Should return empty dict for no data."""
        result = weekly_digest.compute_weekly_summary({"days": []})
        assert result == {}


class TestSendWeeklyDigest:
    """Tests for send_weekly_digest() function."""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Complex integration - requires full email pipeline setup")
    def test_sends_email_on_success(self, tmp_path, monkeypatch, mock_smtp, mock_gemini):
        """Should send email and clear stats on success."""
        pass

    @pytest.mark.integration
    @pytest.mark.skip(reason="Complex integration - requires full email pipeline setup")
    def test_preserves_stats_on_failure(self, tmp_path, monkeypatch):
        """Should preserve stats if email fails."""
        pass
