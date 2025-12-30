#!/usr/bin/env python3
"""Simple HTTP server for serving timelapse files.

Serves files from /app/data/www/ on port 8080.
Access via Tailscale: http://100.94.172.114:8080/timelapses/
"""

import http.server
import os
import socketserver
from datetime import datetime
from functools import partial


from utils.logger import create_logger

log = create_logger("web_server")


WWW_ROOT = os.getenv("WWW_ROOT", "/app/data/www")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with quieter logging."""

    def log_message(self, format, *args):
        # Only log actual file requests, not every connection
        if args and "200" in str(args):
            log(f"{self.address_string()} - {args[0]}")

    def log_error(self, format, *args):
        log(f"ERROR: {format % args}")


def main():
    # Ensure www directories exist
    os.makedirs(os.path.join(WWW_ROOT, "timelapses"), exist_ok=True)

    # Create index.html for the root
    index_path = os.path.join(WWW_ROOT, "index.html")
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Greenhouse Gazette Files</title>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        h1 { color: #2d5a27; }
        a { color: #4a7c43; }
        .dir { margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 8px; }
    </style>
</head>
<body>
    <h1>Greenhouse Gazette Files</h1>
    <div class="dir">
        <h3><a href="/timelapses/">Timelapses</a></h3>
        <p>Monthly and yearly timelapse videos (MP4)</p>
    </div>
</body>
</html>
""")

    # Change to www root directory
    os.chdir(WWW_ROOT)

    handler = partial(QuietHandler, directory=WWW_ROOT)

    with socketserver.TCPServer(("0.0.0.0", WEB_PORT), handler) as httpd:
        log(f"Serving {WWW_ROOT} on port {WEB_PORT}")
        log(f"Access via Tailscale: http://100.94.172.114:{WEB_PORT}/")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
