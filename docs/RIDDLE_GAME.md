# Riddle Referee: Interactive Riddle Game

The Greenhouse Gazette includes an interactive riddle game where newsletter recipients can email their guesses and compete on a leaderboard.

## Overview

Each daily newsletter contains a riddle from "The Canal Captain." Recipients can reply with their guess, and the system will:
1. Judge the answer using AI (with fuzzy matching for synonyms)
2. Send a personalized reply in the Captain's voice
3. Track scores on a season leaderboard

## How to Play

### Submitting a Guess

Click the "Email Your Guess" button in the newsletter, or send an email with subject:
```
GUESS [YYYY-MM-DD]: your answer here
```

The date in brackets must match the riddle's date (shown in the email).

### Scoring

| Action | Points |
|--------|--------|
| Correct answer | +2 |
| First to solve (speed bonus) | +1 additional (total: 3) |
| Wrong guess | 0 (unlimited retries) |

- You can only score **once per riddle** (no spam-farming points)
- First solver is determined by email send timestamp, not processing order

### Leaderboard

The top 5 players are shown in each newsletter. Stats tracked:
- **Points** - Total accumulated score
- **Wins** - Number of times you were first to solve

## Architecture

### Data Files

| File | Purpose | Lifecycle |
|------|---------|-----------|
| `riddle_daily_log.json` | Today's attempts and solvers | Reset after each newsletter |
| `riddle_scores.json` | Season leaderboard | Persistent |
| `riddle_game_archive.json` | Historical daily logs | Rolling 90-day retention |
| `riddle_state.json` | Current riddle and answer | Updated when riddle generated |

### Components

```
inbox_monitor.py     - Polls inbox for GUESS emails (every 5 min)
scorekeeper.py       - Game logic, scoring, leaderboard
narrator.judge_riddle() - AI judging with fuzzy match fallback
publisher.py         - Injects leaderboard into newsletter
```

### Email Flow

```
1. User sends: GUESS [2026-01-12]: the wind
2. inbox_monitor receives email
3. Validates date matches current riddle
4. narrator.judge_riddle() evaluates guess
5. scorekeeper.record_attempt() updates scores
6. Auto-reply sent with result
```

## Safety Features

### Anti-Loop Protection
- Ignores auto-reply emails (checks headers)
- Sets `Auto-Submitted: auto-replied` on outgoing replies
- Rate limit: Max 5 replies per user per 24 hours

### Sender Validation
- Only newsletter recipients can submit guesses
- Admin commands (BROADCAST, INJECT) require separate allow-list

### Input Sanitization
- User guesses truncated to 200 characters
- AI prompt includes injection resistance instructions
- Fallback to simple string matching if AI fails

## Configuration

The game can be disabled via config:
```python
# app/config.py
riddle_game_enabled: bool = True  # Set False to disable
```

Environment variables:
```
RIDDLE_DAILY_LOG_PATH=/app/data/riddle_daily_log.json
RIDDLE_SCORES_PATH=/app/data/riddle_scores.json
RIDDLE_GAME_ARCHIVE_PATH=/app/data/riddle_game_archive.json
```

## Admin Commands

Admins can still use existing commands alongside the game:
- `BROADCAST: Title` - Add announcement card to newsletter
- `INJECT: Message` - Inject content into narrative
- `INJECT HIGH: Message` - High-priority injection

## Troubleshooting

### "That riddle is ancient history"
The date in your subject doesn't match today's riddle. Check the newsletter for the correct date.

### No reply received
- Check spam folder
- You may have hit the rate limit (5 replies/day)
- The inbox is polled every 5 minutes, so replies aren't instant
- Wrong guesses now include a reminder of the riddle text in the reply

### Leaderboard not updating
Scores update immediately, but the leaderboard display only refreshes in the next newsletter.

## Future Enhancements

- Weekly/monthly leaderboard resets (seasons)
- Achievement badges
- Streak tracking
- Difficulty-based bonus points
