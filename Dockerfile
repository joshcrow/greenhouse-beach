# =============================================================================
# GREENHOUSE GAZETTE - Multi-Stage Dockerfile
# =============================================================================
# Stages:
#   - base: System dependencies shared by all stages
#   - deps: Python dependencies (cached layer)
#   - test: Test runner with dev dependencies
#   - frontend-build: Build React frontend with Node.js
#   - production: Final slim production image
#   - web: Production image with web dashboard
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base image with system dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for OpenCV and media processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Dependencies (cached for faster rebuilds)
# -----------------------------------------------------------------------------
FROM base AS deps

# Copy only requirements first (for Docker layer caching)
COPY requirements.txt /app/requirements.txt

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 3: Test runner (includes dev dependencies)
# -----------------------------------------------------------------------------
FROM deps AS test

# Install test dependencies (already in requirements.txt, but explicit for clarity)
RUN pip install --no-cache-dir pytest pytest-cov pytest-mock responses freezegun

# Copy all source code and tests
COPY app /app/app
COPY scripts /app/scripts
COPY configs /app/configs
COPY tests /app/tests
COPY pytest.ini /app/pytest.ini

# Run tests as default command for this stage
CMD ["pytest", "tests/", "-v", "--tb=short"]

# -----------------------------------------------------------------------------
# Stage 4: Production image (minimal, no test deps)
# -----------------------------------------------------------------------------
FROM deps AS production

# Create non-root user for security
RUN groupadd --gid 1000 greenhouse \
    && useradd --uid 1000 --gid greenhouse --shell /bin/bash --create-home greenhouse

# Copy application code
COPY --chown=greenhouse:greenhouse app /app/app
COPY --chown=greenhouse:greenhouse scripts /app/scripts
COPY --chown=greenhouse:greenhouse configs /app/configs

# Create data directories
RUN mkdir -p /app/data/incoming /app/data/archive \
    && chown -R greenhouse:greenhouse /app/data

# Copy and set permissions on entrypoint
COPY --chown=greenhouse:greenhouse scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER greenhouse

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/data/status.json') else 1)" || exit 1

# Labels for container metadata
LABEL org.opencontainers.image.title="Greenhouse Gazette Storyteller" \
      org.opencontainers.image.description="AI-powered greenhouse monitoring and narrative email system" \
      org.opencontainers.image.vendor="Project Chlorophyll" \
      org.opencontainers.image.source="https://github.com/joshcrow/greenhouse-beach"

# Default command
CMD ["/app/entrypoint.sh"]

# -----------------------------------------------------------------------------
# Stage 5: Frontend build (React with Vite)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /app/web

# Copy package files first for caching
COPY web/frontend/package.json ./

# Install dependencies (generates package-lock.json)
RUN npm install

# Copy source and build
COPY web/frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 6: Web Dashboard (FastAPI + React)
# -----------------------------------------------------------------------------
FROM deps AS web

# Create non-root user for security
RUN groupadd --gid 1000 greenhouse \
    && useradd --uid 1000 --gid greenhouse --shell /bin/bash --create-home greenhouse

# Copy application code
COPY --chown=greenhouse:greenhouse app /app/app
COPY --chown=greenhouse:greenhouse scripts /app/scripts
COPY --chown=greenhouse:greenhouse configs /app/configs
COPY --chown=greenhouse:greenhouse web/api /app/web/api
COPY --chown=greenhouse:greenhouse web/__init__.py /app/web/__init__.py

# Copy built frontend from frontend-build stage
COPY --from=frontend-build --chown=greenhouse:greenhouse /app/web/dist /app/web/dist

# Create data directories
RUN mkdir -p /app/data/incoming /app/data/archive \
    && chown -R greenhouse:greenhouse /app/data

# Switch to non-root user
USER greenhouse

# Expose API port
EXPOSE 8000

# Health check for web service
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Labels
LABEL org.opencontainers.image.title="Greenhouse Gazette Web Dashboard" \
      org.opencontainers.image.description="Web dashboard for greenhouse monitoring"

# Run FastAPI with uvicorn
CMD ["python", "-m", "uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
