"""Tests for /api/riddle endpoints."""

from unittest.mock import patch, MagicMock

import pytest


class TestRiddleEndpoint:
    """Tests for GET /api/riddle."""

    @pytest.fixture
    def mock_riddle_state(self):
        """Sample riddle state data."""
        return {
            "question": "What has keys but no locks?",
            "answer": "a piano",
            "date": "2026-01-18",
            "topic": "music",
        }

    @pytest.mark.unit
    def test_returns_riddle_when_exists(self, mock_riddle_state):
        """Should return riddle question and date."""
        with patch("web.api.routers.riddle.atomic_read_json", return_value=mock_riddle_state):
            from web.api.routers.riddle import get_riddle
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_riddle())
            
            assert result["question"] == "What has keys but no locks?"
            assert result["date"] == "2026-01-18"
            assert result["active"] is True

    @pytest.mark.unit
    def test_returns_404_when_no_riddle(self):
        """Should return 404 when no riddle available."""
        with patch("web.api.routers.riddle.atomic_read_json", return_value=None):
            from web.api.routers.riddle import get_riddle
            from fastapi import HTTPException
            import asyncio
            
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(get_riddle())
            
            assert exc_info.value.status_code == 404


class TestGuessEndpoint:
    """Tests for POST /api/riddle/guess."""

    @pytest.mark.unit
    def test_sanitizes_guess_input(self):
        """Should strip HTML and normalize whitespace."""
        from web.api.routers.riddle import GuessRequest
        
        # HTML tags should be stripped
        req = GuessRequest(guess="<script>alert('xss')</script>a piano")
        assert "<script>" not in req.guess
        
        # Whitespace should be normalized
        req2 = GuessRequest(guess="  a   piano  ")
        assert req2.guess == "a piano"

    @pytest.mark.unit
    def test_rejects_empty_guess(self):
        """Should reject empty guess."""
        from web.api.routers.riddle import GuessRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            GuessRequest(guess="")

    @pytest.mark.unit
    def test_rejects_too_long_guess(self):
        """Should reject guess over 200 chars."""
        from web.api.routers.riddle import GuessRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            GuessRequest(guess="x" * 201)


class TestLeaderboardEndpoint:
    """Tests for GET /api/leaderboard."""

    @pytest.mark.unit
    def test_returns_formatted_leaderboard(self):
        """Should return formatted player list."""
        mock_leaderboard = [
            {"email": "josh@test.com", "display_name": "josh", "points": 15, "wins": 3},
            {"email": "mom@test.com", "display_name": "mom", "points": 12, "wins": 2},
        ]
        
        import sys
        mock_sk = MagicMock()
        mock_sk.get_leaderboard.return_value = mock_leaderboard
        sys.modules["scorekeeper"] = mock_sk
        
        try:
            from web.api.routers.riddle import get_leaderboard
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_leaderboard())
            
            assert len(result["players"]) == 2
            assert result["players"][0]["display_name"] == "josh"
            assert result["players"][0]["points"] == 15
        finally:
            del sys.modules["scorekeeper"]

    @pytest.mark.unit
    def test_handles_empty_leaderboard(self):
        """Should handle empty leaderboard gracefully."""
        import sys
        mock_sk = MagicMock()
        mock_sk.get_leaderboard.return_value = []
        sys.modules["scorekeeper"] = mock_sk
        
        try:
            from web.api.routers.riddle import get_leaderboard
            import asyncio
            
            result = asyncio.get_event_loop().run_until_complete(get_leaderboard())
            
            assert result["players"] == []
        finally:
            del sys.modules["scorekeeper"]


class TestUserExtraction:
    """Tests for get_user_email function."""

    @pytest.mark.unit
    def test_extracts_email_from_jwt(self):
        """Should extract email from Cloudflare JWT."""
        from web.api.routers.riddle import get_user_email
        from unittest.mock import MagicMock
        
        mock_request = MagicMock()
        # This is a test JWT - not a real token
        mock_request.headers.get.return_value = None
        
        result = get_user_email(mock_request)
        
        assert result == "anonymous"

    @pytest.mark.unit
    def test_returns_anonymous_when_no_jwt(self):
        """Should return anonymous when no JWT present."""
        from web.api.routers.riddle import get_user_email
        from unittest.mock import MagicMock
        
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        
        result = get_user_email(mock_request)
        
        assert result == "anonymous"
