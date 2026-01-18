# Broadcast Feature — One-Time Narrator Messages

**Status:** ✅ IMPLEMENTED (Production Ready)  
**Goal:** Allow the editor to insert one-time messages into the Greenhouse Gazette via email.

---

## How It Works

1. **Send an email** from your authorized sender address to the Gazette inbox
2. **Subject:** `BROADCAST: Your Title Here`
3. **Body:** Your message content
4. **Wait:** Scheduler polls inbox every 5 minutes
5. **Result:** Message appears in next Gazette with ⚠️ prefix, then auto-deletes

---

## Security

- **Sender whitelist:** Only emails from authorized sender (configured in `broadcast_email.py`) are accepted
- **HTML escaping:** Title and message are sanitized to prevent XSS
- **One-time use:** `broadcast.json` deleted after consumption

---

## Implementation Details

### Email Credentials

A dedicated Gmail account (configured in `.env`) handles both:
- **Sending** the Gazette (SMTP)
- **Receiving** broadcast commands (IMAP)

### Files Modified

| File | Change |
|------|--------|
| `.env` | Updated SMTP credentials to dedicated account |
| `scripts/publisher.py` | Added `build_broadcast_card()` function |
| `scripts/broadcast_email.py` | New — polls inbox for broadcast commands |
| `scripts/scheduler.py` | Added 5-minute broadcast polling job |
| `scripts/test_broadcast.sh` | New — quick testing script |

### Broadcast JSON Format

When a broadcast email is received, it creates `/app/data/broadcast.json`:

```json
{
  "title": "Your Title Here",
  "message": "Your message content",
  "queued_at": "2025-12-28T03:45:00Z"
}
```

This file is consumed (read + deleted) when the next Gazette is sent.

---

## Usage

### Send a Broadcast

From your authorized sender address (phone, web, etc.):

```
To: <GAZETTE_EMAIL>
Subject: BROADCAST: 🔧 System Update
Body: We've upgraded the riddle format! Answers are now revealed the next day.
```

### Timing

- **Polling:** Every 5 minutes
- **Delivery:** Next scheduled Gazette (7:00 AM daily, or Sunday for Weekly Edition)
- **For immediate test:** `./scripts/test_broadcast.sh "Your message"`

### Test Script

```bash
# Full test: creates broadcast.json and sends test email
./scripts/test_broadcast.sh "Your test message here"

# Just poll inbox (after sending email manually)
./scripts/test_broadcast.sh --poll-only

# Just send (if broadcast.json already exists)
./scripts/test_broadcast.sh --send-only
```

### Manual Override (SSH)

```bash
# Create broadcast directly (bypasses email)
echo '{"title": "🔧 System Update", "message": "New feature!"}' > /home/joshcrow/greenhouse-beach/data/broadcast.json
```

---

## Card Appearance

The broadcast card renders with:
- **Purple border** (`#a855f7`) — distinct from green sensor cards
- **Purple header** with ⚠️ caution emoji
- **Header outside card** — consistent with other sections
- **Position:** After headline, before main body
- **Dark mode:** Full support, text remains readable

---

## Troubleshooting

### Broadcast not appearing?

1. Check email was sent FROM your authorized sender address
2. Check email was sent TO the Gazette inbox (see `.env`)
3. Check subject starts with `BROADCAST:`
4. Check scheduler logs: `docker logs greenhouse-storyteller | grep broadcast`
5. Verify file exists: `ls -la data/broadcast.json`

### Test the polling manually

```bash
docker exec -w /app/scripts greenhouse-storyteller python -c "import broadcast_email; broadcast_email.check_for_broadcast()"
```
