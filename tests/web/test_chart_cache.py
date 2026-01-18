"""Tests for ChartCache service."""

import sys
import time
from unittest.mock import patch, MagicMock

import pytest

# Mock chart_generator before importing chart_cache
mock_chart_gen = MagicMock()
sys.modules["chart_generator"] = mock_chart_gen


class TestChartCache:
    """Tests for ChartCache class."""

    @pytest.fixture
    def chart_cache(self):
        """Create a fresh ChartCache instance."""
        from web.api.services.chart_cache import ChartCache
        return ChartCache()

    @pytest.mark.unit
    def test_generates_chart_on_cache_miss(self, chart_cache):
        """Should generate chart when not in cache."""
        mock_png = b"fake png bytes"
        mock_chart_gen.generate_weather_dashboard.return_value = mock_png
        
        result = chart_cache.get_chart(24)
        
        assert result == mock_png

    @pytest.mark.unit
    def test_returns_cached_chart(self, chart_cache):
        """Should return cached chart without regenerating."""
        mock_png = b"fake png bytes"
        mock_chart_gen.generate_weather_dashboard.reset_mock()
        mock_chart_gen.generate_weather_dashboard.return_value = mock_png
        
        # First call generates
        result1 = chart_cache.get_chart(24)
        # Second call should use cache
        result2 = chart_cache.get_chart(24)
        
        assert result1 == mock_png
        assert result2 == mock_png
        # Should only generate once
        assert mock_chart_gen.generate_weather_dashboard.call_count == 1

    @pytest.mark.unit
    def test_regenerates_after_ttl(self):
        """Should regenerate chart after TTL expires."""
        mock_png = b"fake png bytes"
        mock_chart_gen.generate_weather_dashboard.reset_mock()
        mock_chart_gen.generate_weather_dashboard.return_value = mock_png
        
        with patch("web.api.services.chart_cache.CACHE_TTL_SECONDS", 0):  # Immediate expiry
            from web.api.services.chart_cache import ChartCache
            cache = ChartCache()
            # First call generates
            cache.get_chart(24)
            # Allow time to pass (TTL = 0)
            time.sleep(0.1)
            # Second call should regenerate
            cache.get_chart(24)
            
            assert mock_chart_gen.generate_weather_dashboard.call_count == 2

    @pytest.mark.unit
    def test_returns_stale_cache_on_generation_failure(self):
        """Should return stale cache if generation fails."""
        from web.api.services.chart_cache import ChartCache, CachedChart
        
        cache = ChartCache()
        mock_png = b"fake png bytes"
        
        # Pre-populate with stale cache
        cache._cache["24h"] = CachedChart(
            png_bytes=mock_png,
            generated_at=time.time() - 1000,  # Stale
            hours=24,
        )
        
        # Generation fails
        mock_chart_gen.generate_weather_dashboard.side_effect = Exception("Gen failed")
        
        result = cache.get_chart(24)
        
        # Should return stale cache
        assert result == mock_png
        
        # Reset side effect
        mock_chart_gen.generate_weather_dashboard.side_effect = None

    @pytest.mark.unit
    def test_returns_none_on_generation_failure_no_cache(self):
        """Should return None if generation fails and no cache exists."""
        from web.api.services.chart_cache import ChartCache
        
        cache = ChartCache()
        mock_chart_gen.generate_weather_dashboard.side_effect = Exception("Gen failed")
        
        result = cache.get_chart(72)  # Use different hours to avoid cache
        
        assert result is None
        
        # Reset side effect
        mock_chart_gen.generate_weather_dashboard.side_effect = None

    @pytest.mark.unit
    def test_caches_different_ranges_separately(self):
        """Should cache different time ranges independently."""
        from web.api.services.chart_cache import ChartCache
        
        cache = ChartCache()
        mock_24h = b"24h png"
        mock_7d = b"7d png"
        
        mock_chart_gen.generate_weather_dashboard.reset_mock()
        mock_chart_gen.generate_weather_dashboard.side_effect = [mock_24h, mock_7d]
        
        result_24h = cache.get_chart(24)
        result_7d = cache.get_chart(168)
        
        assert result_24h == mock_24h
        assert result_7d == mock_7d
        assert mock_chart_gen.generate_weather_dashboard.call_count == 2
        
        # Reset side effect
        mock_chart_gen.generate_weather_dashboard.side_effect = None

    @pytest.mark.unit
    def test_invalidate_specific_range(self):
        """Should invalidate only specified range."""
        from web.api.services.chart_cache import ChartCache
        
        cache = ChartCache()
        mock_png = b"fake png bytes"
        mock_chart_gen.generate_weather_dashboard.return_value = mock_png
        mock_chart_gen.generate_weather_dashboard.side_effect = None
        
        cache.get_chart(24)
        cache.get_chart(168)
        
        # Invalidate only 24h
        cache.invalidate(hours=24)
        
        assert "24h" not in cache._cache
        assert "168h" in cache._cache

    @pytest.mark.unit
    def test_invalidate_all(self):
        """Should invalidate all ranges when hours=None."""
        from web.api.services.chart_cache import ChartCache
        
        cache = ChartCache()
        mock_png = b"fake png bytes"
        mock_chart_gen.generate_weather_dashboard.return_value = mock_png
        mock_chart_gen.generate_weather_dashboard.side_effect = None
        
        cache.get_chart(24)
        cache.get_chart(168)
        
        cache.invalidate()
        
        assert len(cache._cache) == 0
