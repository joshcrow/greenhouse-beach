#!/usr/bin/env python3
"""Test/Simulation script for the Riddle Referee game.

Usage:
    # Simulate a guess (no email sent)
    python test_riddle_game.py --guess "the wind"
    
    # Simulate with specific user
    python test_riddle_game.py --guess "the wind" --user "mom@example.com"
    
    # Show current game state
    python test_riddle_game.py --status
    
    # Add test players to leaderboard
    python test_riddle_game.py --seed-leaderboard
    
    # Reset game data (fresh start)
    python test_riddle_game.py --reset
    
    # Test AI judging only (no scoring)
    python test_riddle_game.py --judge "the wind"
"""

import argparse
import json
import sys
from datetime import datetime

# Add scripts to path
sys.path.insert(0, "/app/scripts")

from utils.logger import create_logger

log = create_logger("test_riddle")


def show_status():
    """Show current riddle game state."""
    import scorekeeper
    import narrator
    
    print("\n" + "=" * 60)
    print("RIDDLE GAME STATUS")
    print("=" * 60)
    
    # Current riddle
    state = narrator._load_riddle_state()
    print(f"\n📝 Current Riddle:")
    print(f"   Date: {state.get('date', 'N/A')}")
    print(f"   Riddle: {state.get('riddle', 'N/A')[:80]}...")
    print(f"   Answer: {state.get('answer', 'N/A')}")
    
    # Today's solvers
    winners = scorekeeper.get_yesterdays_winners()
    print(f"\n🏆 Today's Solvers: {len(winners)}")
    for w in winners:
        first = " (FIRST!)" if w.get("is_first") else ""
        print(f"   - {w['display_name']}{first}")
    
    # Leaderboard
    leaderboard = scorekeeper.get_leaderboard(top_n=10)
    print(f"\n📊 Leaderboard ({len(leaderboard)} players):")
    for i, p in enumerate(leaderboard, 1):
        print(f"   {i}. {p['display_name']}: {p['points']} pts ({p['wins']} wins)")
    
    print("\n" + "=" * 60)


def test_judge(guess: str):
    """Test AI judging without recording score."""
    import narrator
    
    state = narrator._load_riddle_state()
    if not state.get("answer"):
        print("ERROR: No current riddle found")
        return
    
    print(f"\n🎯 Testing AI Judge")
    print(f"   Riddle: {state.get('riddle', '')[:60]}...")
    print(f"   Answer: {state.get('answer')}")
    print(f"   Your guess: {guess}")
    print()
    
    result = narrator.judge_riddle(
        user_guess=guess,
        correct_answer=state.get("answer", ""),
        riddle_text=state.get("riddle", "")
    )
    
    print(f"   Correct: {'✅ YES' if result['correct'] else '❌ NO'}")
    print(f"   Reply: {result['reply_text']}")


def simulate_guess(guess: str, user_email: str):
    """Simulate a full guess flow without email."""
    import narrator
    import scorekeeper
    
    state = narrator._load_riddle_state()
    if not state.get("answer"):
        print("ERROR: No current riddle found")
        return
    
    riddle_date = state.get("date", datetime.now().date().isoformat())
    
    print(f"\n📧 Simulating Guess")
    print(f"   From: {user_email}")
    print(f"   Subject: GUESS [{riddle_date}]: {guess}")
    print()
    
    # Judge
    judgment = narrator.judge_riddle(
        user_guess=guess,
        correct_answer=state.get("answer", ""),
        riddle_text=state.get("riddle", "")
    )
    
    # Record
    result = scorekeeper.record_attempt(
        user_email=user_email,
        guess_is_correct=judgment["correct"],
        riddle_date=riddle_date,
        email_timestamp=datetime.utcnow()
    )
    
    # Build reply
    reply = judgment["reply_text"]
    if result["status"] == "correct":
        if result.get("is_first"):
            reply += f" First to crack it today! +{result['points']} points."
        else:
            reply += f" +{result['points']} point. You're #{result['rank']} to solve it."
    elif result["status"] == "already_solved":
        reply = "Ye already cracked this one, matey. Save yer ink for tomorrow's riddle."
    elif result["status"] == "stale_riddle":
        reply = "That riddle's from another tide. Check the latest Gazette."
    
    print(f"📬 Reply that would be sent:")
    print(f"   To: {user_email}")
    print(f"   Subject: Re: GUESS [{riddle_date}]: {guess}")
    print(f"   Body: {reply}")
    print()
    print(f"📊 Result: {result}")


def seed_leaderboard():
    """Add some test players to the leaderboard."""
    import scorekeeper
    from utils.io import atomic_write_json
    
    test_data = {
        "season_start": "2026-01-01",
        "players": {
            "mom@example.com": {
                "display_name": "mom",
                "points": 12,
                "wins": 4,
                "last_played": "2026-01-10"
            },
            "grandma@example.com": {
                "display_name": "grandma",
                "points": 8,
                "wins": 2,
                "last_played": "2026-01-09"
            },
            "nick@example.com": {
                "display_name": "nick",
                "points": 5,
                "wins": 1,
                "last_played": "2026-01-11"
            }
        }
    }
    
    atomic_write_json("/app/data/riddle_scores.json", test_data)
    print("✅ Seeded leaderboard with test players")
    show_status()


def reset_game():
    """Reset all game data."""
    import scorekeeper
    from utils.io import atomic_write_json
    
    today = datetime.now().date().isoformat()
    
    atomic_write_json("/app/data/riddle_scores.json", {
        "season_start": today,
        "players": {}
    })
    
    atomic_write_json("/app/data/riddle_daily_log.json", {
        "riddle_date": today,
        "first_solver": None,
        "first_solve_time": None,
        "solvers": [],
        "attempts": []
    })
    
    print("✅ Reset all game data")
    show_status()


def main():
    parser = argparse.ArgumentParser(description="Test Riddle Referee game")
    parser.add_argument("--guess", "-g", help="Simulate a guess")
    parser.add_argument("--user", "-u", default="test@example.com", help="User email for guess")
    parser.add_argument("--judge", "-j", help="Test AI judging only (no scoring)")
    parser.add_argument("--status", "-s", action="store_true", help="Show game status")
    parser.add_argument("--seed-leaderboard", action="store_true", help="Add test players")
    parser.add_argument("--reset", action="store_true", help="Reset all game data")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.guess:
        simulate_guess(args.guess, args.user)
    elif args.judge:
        test_judge(args.judge)
    elif args.seed_leaderboard:
        seed_leaderboard()
    elif args.reset:
        reset_game()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
