"""Riddle Referee Scorekeeper - Game logic and persistence.

Manages the riddle guessing game:
- Tracks daily attempts and solvers
- Maintains season leaderboard
- Handles first-solver bonus scoring

Data Files:
  data/riddle_daily_log.json - Ephemeral, reset after each newsletter
  data/riddle_scores.json - Persistent season leaderboard
  data/riddle_game_archive.json - Historical archive of daily logs
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from utils.io import atomic_write_json, atomic_read_json
from utils.logger import create_logger

log = create_logger("scorekeeper")

# Lazy settings loader to avoid import-time failures
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings


def _get_daily_log_path():
    s = _get_settings()
    return s.riddle_daily_log_path if s else "/app/data/riddle_daily_log.json"


def _get_scores_path():
    s = _get_settings()
    return s.riddle_scores_path if s else "/app/data/riddle_scores.json"


def _get_archive_path():
    s = _get_settings()
    return s.riddle_archive_path if s else "/app/data/riddle_game_archive.json"

# Scoring constants
POINTS_CORRECT = 2        # Points for a correct answer
POINTS_FIRST_BONUS = 1    # Additional point for first solver (total: 3)


def _empty_daily_log(date: str) -> Dict[str, Any]:
    """Create an empty daily log structure."""
    return {
        "riddle_date": date,
        "first_solver": None,
        "first_solve_time": None,
        "solvers": [],
        "attempts": []
    }


def _empty_scores() -> Dict[str, Any]:
    """Create an empty scores structure."""
    return {
        "season_start": datetime.now().date().isoformat(),
        "players": {}
    }


def _load_daily_log() -> Dict[str, Any]:
    """Load the current daily log."""
    data = atomic_read_json(_get_daily_log_path(), default=None)
    if data is None:
        today = datetime.now().date().isoformat()
        return _empty_daily_log(today)
    return data


def _save_daily_log(data: Dict[str, Any]) -> None:
    """Save the daily log atomically."""
    atomic_write_json(_get_daily_log_path(), data)


def _load_scores() -> Dict[str, Any]:
    """Load the season scores."""
    data = atomic_read_json(_get_scores_path(), default=None)
    if data is None:
        return _empty_scores()
    return data


def _save_scores(data: Dict[str, Any]) -> None:
    """Save scores atomically."""
    atomic_write_json(_get_scores_path(), data)


def get_display_name(email: str) -> str:
    """Extract display name from email prefix (before @)."""
    if not email or "@" not in email:
        return email or "anonymous"
    return email.split("@")[0].lower()


def record_attempt(
    user_email: str,
    guess_is_correct: bool,
    riddle_date: str,
    email_timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Record a guess attempt and update scores if correct.
    
    Args:
        user_email: The guesser's email address
        guess_is_correct: Whether the AI judged the guess correct
        riddle_date: The date ID of the riddle being guessed
        email_timestamp: When the email was sent (for fair first-solver)
    
    Returns:
        {"status": "already_solved"} - User already got this riddle
        {"status": "wrong"} - Incorrect guess
        {"status": "correct", "points": 1|2, "is_first": bool, "rank": int}
        {"status": "stale_riddle"} - Riddle date doesn't match current
    """
    user_email = user_email.lower().strip()
    display_name = get_display_name(user_email)
    now = datetime.utcnow()
    email_ts = email_timestamp or now
    
    daily_log = _load_daily_log()
    
    # Check if this is for the current riddle
    if daily_log.get("riddle_date") != riddle_date:
        log(f"Stale riddle guess from {display_name}: {riddle_date} vs current {daily_log.get('riddle_date')}")
        return {"status": "stale_riddle"}
    
    # Record the attempt
    attempt = {
        "user": user_email,
        "display_name": display_name,
        "correct": guess_is_correct,
        "email_timestamp": email_ts.isoformat() + "Z",
        "processed_at": now.isoformat() + "Z"
    }
    daily_log.setdefault("attempts", []).append(attempt)
    
    # If wrong, just save and return
    if not guess_is_correct:
        _save_daily_log(daily_log)
        log(f"Wrong guess from {display_name}")
        return {"status": "wrong"}
    
    # Check if user already solved this riddle
    solvers = daily_log.get("solvers", [])
    if user_email in solvers:
        _save_daily_log(daily_log)
        log(f"Duplicate solve attempt from {display_name}")
        return {"status": "already_solved"}
    
    # Correct answer! Determine if first solver
    is_first = False
    points = POINTS_CORRECT
    
    current_first_time = daily_log.get("first_solve_time")
    if current_first_time:
        # Compare with existing first solver time
        first_dt = datetime.fromisoformat(current_first_time.replace("Z", "+00:00")).replace(tzinfo=None)
        if email_ts < first_dt:
            # This user actually sent their email earlier - they're the real first
            is_first = True
            points = POINTS_CORRECT + POINTS_FIRST_BONUS
            daily_log["first_solver"] = user_email
            daily_log["first_solve_time"] = email_ts.isoformat() + "Z"
            log(f"{display_name} is the NEW first solver (earlier email timestamp)")
    else:
        # No first solver yet
        is_first = True
        points = POINTS_CORRECT + POINTS_FIRST_BONUS
        daily_log["first_solver"] = user_email
        daily_log["first_solve_time"] = email_ts.isoformat() + "Z"
        log(f"{display_name} is the first solver!")
    
    # Add to solvers list
    solvers.append(user_email)
    daily_log["solvers"] = solvers
    _save_daily_log(daily_log)
    
    # Update season scores
    scores = _load_scores()
    players = scores.setdefault("players", {})
    
    if user_email not in players:
        players[user_email] = {
            "display_name": display_name,
            "points": 0,
            "wins": 0,
            "last_played": riddle_date
        }
    
    player = players[user_email]
    player["points"] = player.get("points", 0) + points
    if is_first:
        player["wins"] = player.get("wins", 0) + 1
    player["last_played"] = riddle_date
    
    _save_scores(scores)
    
    # Calculate rank (position in today's solvers)
    rank = len(solvers)
    
    log(f"Correct! {display_name} earned {points} points (first={is_first}, rank={rank})")
    
    return {
        "status": "correct",
        "points": points,
        "is_first": is_first,
        "rank": rank
    }


def get_season_start() -> str:
    """Return the season start date from scores file."""
    scores = _load_scores()
    return scores.get("season_start", datetime.now().date().isoformat())


def get_leaderboard(top_n: int = 5) -> List[Dict[str, Any]]:
    """Return top N players sorted by points."""
    scores = _load_scores()
    players = scores.get("players", {})
    
    # Convert to list and sort by points (desc), then by wins (desc)
    player_list = [
        {
            "email": email,
            "display_name": info.get("display_name", get_display_name(email)),
            "points": info.get("points", 0),
            "wins": info.get("wins", 0)
        }
        for email, info in players.items()
    ]
    
    player_list.sort(key=lambda x: (-x["points"], -x["wins"]))
    
    return player_list[:top_n]


def get_yesterdays_winners() -> List[Dict[str, Any]]:
    """Return solvers from riddle_daily_log for email display."""
    daily_log = _load_daily_log()
    solvers = daily_log.get("solvers", [])
    first_solver = daily_log.get("first_solver")
    
    result = []
    for email in solvers:
        result.append({
            "email": email,
            "display_name": get_display_name(email),
            "is_first": email == first_solver
        })
    
    # Sort so first solver is at the top
    result.sort(key=lambda x: (not x["is_first"], x["display_name"]))
    
    return result


def reset_daily_log(new_date: str) -> None:
    """Reset daily log for new riddle (called after email send)."""
    log(f"Resetting daily log for {new_date}")
    _save_daily_log(_empty_daily_log(new_date))


def archive_daily_log() -> None:
    """Append current daily log to riddle_game_archive.json."""
    daily_log = _load_daily_log()
    
    # Don't archive empty logs
    if not daily_log.get("attempts") and not daily_log.get("solvers"):
        log("No attempts to archive, skipping")
        return
    
    archive = atomic_read_json(_get_archive_path(), default=[])
    if not isinstance(archive, list):
        archive = []
    
    # Add timestamp for when archived
    daily_log["archived_at"] = datetime.utcnow().isoformat() + "Z"
    archive.append(daily_log)
    
    # Keep last 90 days of archives
    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
    archive = [
        entry for entry in archive
        if entry.get("riddle_date", "") >= cutoff[:10]
    ]
    
    atomic_write_json(_get_archive_path(), archive)
    log(f"Archived daily log for {daily_log.get('riddle_date')}")


def get_player_stats(user_email: str) -> Optional[Dict[str, Any]]:
    """Get stats for a specific player."""
    user_email = user_email.lower().strip()
    scores = _load_scores()
    players = scores.get("players", {})
    
    if user_email not in players:
        return None
    
    player = players[user_email]
    
    # Calculate rank
    leaderboard = get_leaderboard(top_n=100)
    rank = next(
        (i + 1 for i, p in enumerate(leaderboard) if p["email"] == user_email),
        None
    )
    
    return {
        "email": user_email,
        "display_name": player.get("display_name", get_display_name(user_email)),
        "points": player.get("points", 0),
        "wins": player.get("wins", 0),
        "last_played": player.get("last_played"),
        "rank": rank
    }


if __name__ == "__main__":
    # Quick test
    print("Leaderboard:", get_leaderboard())
    print("Yesterday's winners:", get_yesterdays_winners())
