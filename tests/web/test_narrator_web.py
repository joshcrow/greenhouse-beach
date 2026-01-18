"""Tests for narrator.generate_narrative_only() function.

These tests verify the web-safe narrative generation function exists
and has the expected interface. Full integration tests require the
google-genai module which may not be available in all environments.
"""

import pytest

# Skip all tests in this module if google-genai is not installed
pytest.importorskip("google.genai", reason="google-genai required for narrator tests")


class TestGenerateNarrativeOnly:
    """Tests for the web-safe narrative generation function."""

    @pytest.mark.unit
    def test_function_exists(self):
        """Should have generate_narrative_only function."""
        import narrator
        assert hasattr(narrator, "generate_narrative_only")
        assert callable(narrator.generate_narrative_only)

    @pytest.mark.unit
    def test_function_signature(self):
        """Should accept sensor_data and optional model_name."""
        import inspect
        import narrator
        
        sig = inspect.signature(narrator.generate_narrative_only)
        params = list(sig.parameters.keys())
        
        assert "sensor_data" in params
        assert "model_name" in params
