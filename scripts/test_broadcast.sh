#!/bin/bash
# Quick broadcast test script
# Usage: ./test_broadcast.sh "Your message here"
#        ./test_broadcast.sh --poll-only    (just poll inbox, don't send)
#        ./test_broadcast.sh --send-only    (just send, use existing broadcast.json)

set -e
cd "$(dirname "$0")/.."

MESSAGE="${1:-Test broadcast message}"

# Check for flags
if [[ "$1" == "--poll-only" ]]; then
    echo "📬 Polling inbox for broadcast emails..."
    docker exec -w /app/scripts greenhouse-storyteller python -c "import broadcast_email; result = broadcast_email.check_for_broadcast(); print(f'Found broadcast: {result}')"
    exit 0
fi

if [[ "$1" == "--send-only" ]]; then
    echo "📧 Sending test email (using existing broadcast.json if present)..."
    docker exec -w /app/scripts greenhouse-storyteller python -c "
import publisher
publisher._test_mode = True
publisher.is_weekly_edition = lambda: False
import os
os.environ['SMTP_TO'] = 'joshcrow1193@gmail.com'
publisher.run_once()
"
    exit 0
fi

# Full test: create broadcast, then send
echo "📝 Creating broadcast.json..."
echo "{\"title\": \"Test Broadcast\", \"message\": \"$MESSAGE\"}" > data/broadcast.json
echo "✅ Created: data/broadcast.json"

echo ""
echo "📧 Sending test email..."
docker exec -w /app/scripts greenhouse-storyteller python -c "
import publisher
publisher._test_mode = True
publisher.is_weekly_edition = lambda: False
import os
os.environ['SMTP_TO'] = 'joshcrow1193@gmail.com'
publisher.run_once()
"

echo ""
echo "✅ Done! Check joshcrow1193@gmail.com for test email."
