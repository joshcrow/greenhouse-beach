FROM python:3.11-slim-bookworm

# Install system dependencies for media processing and OpenCV/YOLO
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    opencv-python-headless \
    paho-mqtt \
    requests \
    google-generativeai \
    schedule \
    python-dotenv \
    Pillow

# Copy application code and configs
COPY scripts /app/scripts
COPY configs /app/configs

# Entrypoint orchestrates ingestion and curator services
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
