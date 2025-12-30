# Email Redesign Beta Testing

## Branch: `beta/email-redesign-v1`

This document describes the beta email redesign and how to test it.

## What Changed

### Visual Design
- **Removed heavy green borders** — Cards now use subtle gray backgrounds instead of `2px solid #6b9b5a` borders
- **Consolidated data tables** — Merged 4 separate tables (Sensors, Weather, 24h Stats, Weekly Stats) into 2 clean sections
- **Icon-anchored alerts** — Alert banner now uses emojis (❄️ frost, 💨 wind, 🔋 battery) with separated warning/detail text
- **Large temperature display** — Side-by-side Greenhouse vs Outside temps with prominent numbers
- **Removed battery voltage** — No longer showing `3.7V` noise in the UI

### Section Structure (Maintained Order)
1. Header (Date/Subject)
2. Alert Banner (if any)
3. Narrative Text Summary
4. Brain Fart (Riddle)
5. Hero (Timelapse)
6. **📍 Current Conditions** — Merged sensors + weather into one card
7. **📈 Trends** — Chart + H/L summary (daily: 24h, weekly: 7d)

### Files
- `scripts/publisher_beta.py` — Beta version with redesigned email template
- `scripts/publisher.py` — Production version (unchanged)

## Testing Workflow

### Send Test Email (Daily)
```bash
docker compose exec storyteller python /app/scripts/publisher_beta.py --test --daily
```

### Send Test Email (Weekly)
```bash
docker compose exec storyteller python /app/scripts/publisher_beta.py --test --weekly
```

### Compare Side-by-Side
1. Send production email: `python /app/scripts/publisher.py --test --daily`
2. Send beta email: `python /app/scripts/publisher_beta.py --test --daily`
3. Check inbox and compare visually

## Promotion to Production

When ready to promote beta to production:

```bash
# On the beta branch
cp scripts/publisher_beta.py scripts/publisher.py
git add scripts/publisher.py
git commit -m "feat: Promote email redesign to production"
git checkout main
git merge beta/email-redesign-v1
```

## Rollback

If issues arise after promotion:
```bash
git revert HEAD  # Revert the merge commit
# Or restore from git history
```

## Dark Mode Support

The redesign maintains full dark mode support:
- `.dark-bg-card` — Subtle elevated fill (`#1f1f1f`)
- `.dark-bg-subtle` — Secondary fill (`#262626`)
- `.dark-text-*` classes — All text colors adapt

## Outlook Compatibility

- Uses table-based layout throughout
- Inline CSS for all styles
- MSO conditionals for Outlook-specific fixes
- Max-width 600px container
