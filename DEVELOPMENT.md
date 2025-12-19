# Development Guide

This document covers the development workflow, CI/CD pipeline, and testing for the Greenhouse Gazette project.

---

## Quick Start

```bash
# Clone and setup
git clone git@github.com:joshcrow/greenhouse-beach.git
cd greenhouse-beach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest

# Start local development
docker compose --profile dev up
```

---

## Development Workflow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Edit Locally   │───►│   Run Tests     │───►│   Git Push      │
│  scripts/*.py   │    │   pytest        │    │   to main       │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                       ┌───────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions CI/CD                          │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ Quality Job     │ Build Job       │ Security Job                │
│ • Lint (Ruff)   │ • Docker build  │ • pip-audit                 │
│ • pytest        │ • Push to Hub   │ • Dependency scan           │
│ • Coverage      │ • ARM64 + AMD64 │                             │
└─────────────────┴─────────────────┴─────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Hub                                    │
│                    jcrow333/greenhouse-storyteller               │
│                    Tags: latest, main, sha-xxxxx                 │
└─────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Storyteller Pi                                │
│                    docker pull jcrow333/greenhouse-storyteller   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing

### Run All Tests
```bash
# Local (fast)
pytest

# In Docker (matches CI exactly)
docker compose run --rm test
```

### Run Specific Tests
```bash
pytest tests/test_publisher.py           # Single file
pytest tests/test_narrator.py -k "sanitize"  # By name pattern
pytest -m unit                           # Only unit tests
pytest -m integration                    # Only integration tests
```

### Coverage Report
```bash
pytest --cov=scripts --cov-report=html
open coverage_html/index.html
```

### Test Structure
```
tests/
├── conftest.py           # Shared fixtures
├── test_weather_service.py
├── test_narrator.py
├── test_golden_hour.py
├── test_stats.py
├── test_status_daemon.py
├── test_curator.py
├── test_timelapse.py
├── test_publisher.py
├── test_ingestion.py
├── test_scheduler.py
└── test_weekly_digest.py
```

---

## Docker

### Build Stages
| Stage | Purpose | Command |
|-------|---------|---------|
| `base` | System deps | - |
| `deps` | Python packages | - |
| `test` | Run tests | `docker build --target test .` |
| `production` | Final image | `docker build --target production .` |

### Compose Profiles
```bash
# Production (default)
docker compose up -d

# Run tests
docker compose run --rm test

# Development with hot-reload
docker compose --profile dev up
```

---

## CI/CD Pipeline

### Triggers
- **Push to `main`**: Full pipeline + Docker push
- **Pull Request**: Tests only (no push)

### Jobs
1. **Quality** - Lint + Test + Coverage
2. **Build** - Docker multi-arch build + push
3. **Security** - Dependency vulnerability scan

### GitHub Secrets Required
| Secret | Purpose |
|--------|---------|
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub access token |

### Check CI Status
```bash
gh run list
gh run view
gh run watch  # Live output
```

---

## Deploying to Storyteller Pi

### Fast Deploy (Pre-built Image)
```bash
ssh joshcrow@100.94.172.114
cd ~/greenhouse-beach
docker pull jcrow333/greenhouse-storyteller:latest
docker compose up -d
```

### Manual Build (Slow)
```bash
ssh joshcrow@100.94.172.114
cd ~/greenhouse-beach
git pull
docker compose build
docker compose up -d
```

---

## Code Style

- **Linter**: Ruff (auto-runs in CI)
- **Formatter**: Ruff format
- **Type hints**: Encouraged but not enforced
- **Docstrings**: Required for public functions

### Run Linter Locally
```bash
pip install ruff
ruff check scripts/
ruff format scripts/ --check
```

---

## Project Structure

```
greenhouse-beach/
├── .github/workflows/    # CI/CD pipeline
│   └── ci-cd.yml
├── configs/              # Mosquitto, registry configs
├── data/                 # Runtime data (gitignored)
├── scripts/              # Python application code
│   ├── ingestion.py      # MQTT image receiver
│   ├── curator.py        # Image processing
│   ├── scheduler.py      # Job scheduling
│   ├── status_daemon.py  # Sensor data aggregation
│   ├── publisher.py      # Email builder
│   ├── narrator.py       # AI narrative generation
│   └── ...
├── tests/                # pytest test suite
├── Dockerfile            # Multi-stage build
├── docker-compose.yml    # Service definitions
├── requirements.txt      # Python dependencies
├── pytest.ini           # Test configuration
└── .env.example         # Environment template
```
