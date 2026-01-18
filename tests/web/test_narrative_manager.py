"""Tests for NarrativeManager service."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

# Mock dependencies before importing
mock_narrator = MagicMock()
mock_publisher = MagicMock()
sys.modules["narrator"] = mock_narrator
sys.modules["publisher"] = mock_publisher


class TestNarrativeManager:
    """Tests for NarrativeManager class."""

    @pytest.fixture
    def temp_paths(self, tmp_path):
        """Create temporary paths for cache files."""
        cache_path = str(tmp_path / "narrative_cache.json")
        lock_path = str(tmp_path / "narrative_generation.lock")
        rate_limit_path = str(tmp_path / "narrative_rate_limit.json")
        return cache_path, lock_path, rate_limit_path

    @pytest.mark.unit
    def test_returns_fallback_when_no_cache(self, temp_paths):
        """Should return fallback narrative when no cache exists."""
        cache_path, lock_path, rate_limit_path = temp_paths
        
        with patch("web.api.services.narrative_manager.CACHE_PATH", cache_path), \
             patch("web.api.services.narrative_manager.LOCK_PATH", lock_path), \
             patch("web.api.services.narrative_manager.RATE_LIMIT_PATH", rate_limit_path), \
             patch("web.api.services.narrative_manager.settings", None):
            from web.api.services.narrative_manager import NarrativeManager
            manager = NarrativeManager()
            
            # Mock generation to fail
            with patch.object(manager, "_generate_narrative", side_effect=Exception("No AI")):
                result = manager.get_narrative()
                
                assert result.get("fallback") is True
                assert "Captain" in result.get("subject", "")

    @pytest.mark.unit
    def test_returns_cached_when_fresh(self, temp_paths):
        """Should return cached narrative if not stale."""
        cache_path, lock_path, rate_limit_path = temp_paths
        
        # Pre-populate cache
        now = datetime.utcnow()
        cache_data = {
            "subject": "Test Subject",
            "headline": "Test Headline",
            "body": "Test body content.",
            "generated_at": now.isoformat() + "Z",
            "cached": False,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)
        
        with patch("web.api.services.narrative_manager.CACHE_PATH", cache_path), \
             patch("web.api.services.narrative_manager.LOCK_PATH", lock_path), \
             patch("web.api.services.narrative_manager.RATE_LIMIT_PATH", rate_limit_path), \
             patch("web.api.services.narrative_manager.settings", None):
            from web.api.services.narrative_manager import NarrativeManager
            manager = NarrativeManager()
            
            result = manager.get_narrative()
            
            assert result["subject"] == "Test Subject"
            assert result.get("cached") is False  # Fresh cache

    @pytest.mark.unit
    def test_respects_rate_limit(self, temp_paths):
        """Should return cached narrative when rate limited."""
        cache_path, lock_path, rate_limit_path = temp_paths
        
        # Pre-populate rate limit with 4 recent timestamps
        now = datetime.utcnow()
        timestamps = [
            (now - timedelta(minutes=i * 10)).isoformat() + "Z"
            for i in range(4)
        ]
        with open(rate_limit_path, "w") as f:
            json.dump({"timestamps": timestamps}, f)
        
        # Pre-populate stale cache
        stale_time = (now - timedelta(hours=2)).isoformat() + "Z"
        cache_data = {
            "subject": "Stale Subject",
            "headline": "Stale Headline",
            "body": "Stale body.",
            "generated_at": stale_time,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)
        
        with patch("web.api.services.narrative_manager.CACHE_PATH", cache_path), \
             patch("web.api.services.narrative_manager.LOCK_PATH", lock_path), \
             patch("web.api.services.narrative_manager.RATE_LIMIT_PATH", rate_limit_path), \
             patch("web.api.services.narrative_manager.settings", None):
            from web.api.services.narrative_manager import NarrativeManager
            manager = NarrativeManager()
            
            result = manager.get_narrative(force_refresh=True)
            
            # Should return cached with rate_limited flag
            assert result.get("rate_limited") is True
            assert result.get("cached") is True


class TestCachedNarrative:
    """Tests for CachedNarrative dataclass."""

    @pytest.mark.unit
    def test_is_stale_when_old(self):
        """Should be stale when older than MAX_AGE_MINUTES."""
        from web.api.services.narrative_manager import CachedNarrative
        
        old_time = datetime.utcnow() - timedelta(hours=2)
        narrative = CachedNarrative(
            subject="Test",
            headline="Test",
            body="Test",
            generated_at=old_time,
        )
        
        assert narrative.is_stale() is True

    @pytest.mark.unit
    def test_is_fresh_when_recent(self):
        """Should not be stale when recent."""
        from web.api.services.narrative_manager import CachedNarrative
        
        recent_time = datetime.utcnow() - timedelta(minutes=30)
        narrative = CachedNarrative(
            subject="Test",
            headline="Test",
            body="Test",
            generated_at=recent_time,
        )
        
        assert narrative.is_stale() is False

    @pytest.mark.unit
    def test_to_dict_format(self):
        """Should convert to dict with correct format."""
        from web.api.services.narrative_manager import CachedNarrative
        
        narrative = CachedNarrative(
            subject="Test Subject",
            headline="Test Headline",
            body="Test body.",
            generated_at=datetime(2026, 1, 18, 12, 0, 0),
            cached=True,
        )
        
        result = narrative.to_dict()
        
        assert result["subject"] == "Test Subject"
        assert result["headline"] == "Test Headline"
        assert result["body"] == "Test body."
        assert result["cached"] is True
        assert "2026-01-18" in result["generated_at"]
