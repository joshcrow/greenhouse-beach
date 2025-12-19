"""
Integration tests for scheduler.py

Tests the job scheduling system.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

import scheduler


class TestSafeDailyDispatch:
    """Tests for safe_daily_dispatch() function."""

    @pytest.mark.integration
    def test_calls_publisher_run_once(self):
        """Should call publisher.run_once()."""
        with patch("scheduler.publisher.run_once") as mock_run:
            with patch("scheduler.weekly_digest.record_daily_snapshot"):
                scheduler.safe_daily_dispatch()

        mock_run.assert_called_once()

    @pytest.mark.integration
    def test_records_daily_snapshot(self):
        """Should record daily snapshot for weekly stats."""
        with patch("scheduler.publisher.run_once"):
            with patch("scheduler.weekly_digest.record_daily_snapshot") as mock_record:
                scheduler.safe_daily_dispatch()

        mock_record.assert_called_once()

    @pytest.mark.integration
    def test_handles_publisher_error(self):
        """Should handle publisher errors gracefully."""
        with patch("scheduler.publisher.run_once", side_effect=Exception("Error")):
            with patch("scheduler.weekly_digest.record_daily_snapshot"):
                # Should not raise
                scheduler.safe_daily_dispatch()


class TestTriggerGoldenHourCapture:
    """Tests for trigger_golden_hour_capture() function."""

    @pytest.mark.integration
    def test_logs_trigger(self, capfd):
        """Should log golden hour trigger."""
        scheduler.trigger_golden_hour_capture()

        captured = capfd.readouterr()
        assert "golden hour" in captured.out.lower() or "Golden hour" in captured.out


class TestSchedulerMain:
    """Tests for main scheduler setup."""

    @pytest.mark.integration
    def test_registers_daily_job(self):
        """Should register daily dispatch at 07:00."""
        import schedule as schedule_lib
        schedule_lib.clear()

        with patch("scheduler.schedule.every") as mock_every:
            mock_day = MagicMock()
            mock_every.return_value.day = mock_day
            mock_at = MagicMock()
            mock_day.at.return_value = mock_at

            # Mock golden_hour to avoid API calls
            with patch("scheduler.golden_hour.get_seasonal_golden_hour", return_value="16:00"):
                # Run main but break the loop immediately
                with patch("scheduler.time.sleep", side_effect=KeyboardInterrupt):
                    try:
                        scheduler.main()
                    except KeyboardInterrupt:
                        pass

            # Verify 07:00 job was registered
            mock_day.at.assert_any_call("07:00")

    @pytest.mark.integration
    def test_registers_golden_hour_job(self):
        """Should register golden hour job at seasonal time."""
        import schedule as schedule_lib
        schedule_lib.clear()

        with patch("scheduler.schedule.every") as mock_every:
            mock_day = MagicMock()
            mock_every.return_value.day = mock_day
            mock_at = MagicMock()
            mock_day.at.return_value = mock_at

            with patch("scheduler.golden_hour.get_seasonal_golden_hour", return_value="18:30"):
                with patch("scheduler.time.sleep", side_effect=KeyboardInterrupt):
                    try:
                        scheduler.main()
                    except KeyboardInterrupt:
                        pass

            # Verify golden hour job was registered
            mock_day.at.assert_any_call("18:30")
