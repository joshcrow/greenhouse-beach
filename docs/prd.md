# Product Requirements Document (PRD): Greenhouse Gazette Web

**Codename:** SOC  
**URL:** `https://straightouttacolington.com`

| Metadata | Details |
|:---|:---|
| **Version** | 2.1 (Enhanced Architecture) |
| **Date** | January 18, 2026 |
| **Target Platform** | Web (Mobile-First SPA) |
| **Tech Stack** | React (Vite), Material UI (MUI), FastAPI, Docker |
| **Infrastructure** | Raspberry Pi 5 (NVMe Storage) + Cloudflare Tunnel |

---

## 1. Executive Summary

**Problem:** The Greenhouse Gazette is currently a push-only experience (daily email). Users lack real-time visibility into greenhouse conditions and cannot interact with the system (riddles, historical data) on demand.

**Vision:** Create a **"Living Field Journal"** accessible from anywhere via a custom domain. This web dashboard allows the "Crew" to monitor live vitals, read context-aware narratives that auto-update based on conditions, and interact with the "Canal Captain" persona securely.

**Core Value:**
1. **Immediacy:** Real-time sensor telemetry via a modern, dark-mode interface.
2. **Automation:** Narratives update automatically when users visit, ensuring the "Captain's Log" is always current.
3. **Security:** Enterprise-grade Zero Trust access via Cloudflare, eliminating open ports.

---

## 2. User Personas

1. **The Captain (Admin):** Verifies system health (battery, connectivity) and views raw logs. Needs fast access via mobile while away from home.
2. **The Crew (Family):** Wants to check if it's freezing, read the latest "rant" from the Captain, and solve the daily riddle.

---

## 3. Functional Requirements

### 3.1 Module A: Real-Time Telemetry ("The Gauges")

| ID | Requirement | Notes |
|:---|:---|:---|
| **REQ-A1** | Display normalized sensor data using canonical keys | See §10 Sensor Key Reference |
| **REQ-A2** | **Hybrid Refresh:** WebSocket for push updates; HTTP polling fallback (30s) | WebSocket preferred for "live" feel |
| **REQ-A3** | **Freshness Indicator:** Visual warning if `*_stale` flag is true | Backend provides per-sensor staleness |
| **REQ-A4** | **Battery Health:** Visual voltage bar for `satellite_battery` | Green: ≥3.8V, Yellow: 3.6-3.8V, Red: <3.6V, Critical: <3.4V |
| **REQ-A5** | **Pressure Display:** Show `satellite_pressure` in inHg | Optional metric toggle |

### 3.2 Module B: The Smart Narrative ("Captain's Log")

| ID | Requirement | Notes |
|:---|:---|:---|
| **REQ-B1** | Display the current AI narrative | Cached in `NarrativeManager` |
| **REQ-B2** | **Auto-Generation on Load:** If narrative >60 mins old, regenerate | Uses `narrator.generate_narrative_only()` (new) |
| **REQ-B3** | **Cooldown:** Global file-lock prevents concurrent generation | Returns cached version during lock |
| **REQ-B4** | **Fallback:** If AI API fails, serve last successful narrative with "Cached" badge | Graceful degradation per project rules |
| **REQ-B5** | **Rate Limit:** Max 4 regenerations/hour server-wide | Protects Gemini API quota |
| **REQ-B6** | **Blackout Window:** No regeneration within 30 mins of 07:00 daily email | Prevents stale riddle pollution |

### 3.3 Module C: Interactive Riddle Game

| ID | Requirement | Notes |
|:---|:---|:---|
| **REQ-C1** | Display the active riddle question from `riddle_state.json` | |
| **REQ-C2** | **Direct Input:** Text field for submitting guesses | Max 200 chars, sanitized |
| **REQ-C3** | **Instant Feedback:** Toast notifications (success/failure) | Uses existing `narrator.judge_riddle()` |
| **REQ-C4** | **Leaderboard:** Top 5 scores from `scorekeeper.get_leaderboard()` | |
| **REQ-C5** | **Personal Stats:** User can view own rank/points | Requires user identification |

### 3.4 Module D: Visual Archives ("The Porthole")

| ID | Requirement | Notes |
|:---|:---|:---|
| **REQ-D1** | **Hero View:** Latest camera image from `archive/YYYY/MM/DD/` | |
| **REQ-D2** | **Lightbox:** Full-screen viewer with pinch-zoom (mobile) | |
| **REQ-D3** | **Timelapse Gallery:** Tabs for Daily GIF, Weekly MP4, Monthly MP4 | Served from `data/www/timelapses/` |

### 3.5 Module E: Historical Trends

| ID | Requirement | Notes |
|:---|:---|:---|
| **REQ-E1** | Interactive Line Charts (Recharts) for Temp/Humidity | Reuse `chart_generator.py` design system |
| **REQ-E2** | Range toggle: 24h / 7d / 30d | |
| **REQ-E3** | Data sourced from `sensor_log/*.jsonl` with server-side aggregation | Hourly averages for >48h ranges |
| **REQ-E4** | **[BACKLOG]** SQLite migration for faster range queries | See backlog.md |

---

## 4. Technical Architecture

### 4.1 The Stack (React + FastAPI)

#### Frontend
- **Framework:** React 18 (Vite) + **Material UI (MUI) v6**
- **State:** TanStack Query (React Query) for polling/caching
- **Real-time:** Native WebSocket client with reconnection logic
- **Theme:** Custom MUI Theme (see §7 Design System)

**Why MUI for Figma Pipeline:**
MUI has first-class Figma support via the [MUI Design Kit](https://mui.com/store/items/figma-react/):
- **Figma Components** mirror React components 1:1
- **Design Tokens** exportable to MUI theme
- **Figma Dev Mode** generates component props
- Future: Figma MCP → Windsurf can map Figma layers to MUI component code

**Alternatives Considered:**

| Library | Figma Support | Bundle Size | Verdict |
|:---|:---|:---|:---|
| MUI v6 | ✅ Official kit | ~80KB gzipped | **Selected** - best Figma story |
| Radix + Tailwind | ⚠️ Community kits | ~30KB | Lighter, but Figma mapping is manual |
| Chakra UI | ✅ Official kit | ~60KB | Good, but less mature than MUI |
| shadcn/ui | ⚠️ Unofficial | ~20KB | Copy-paste model complicates Figma sync |

#### Backend
- **Framework:** FastAPI (async)
- **Static Serving:** Serves React build bundle at `/`
- **API:** REST endpoints at `/api/*` + WebSocket at `/ws`
- **Config:** Uses `app.config.settings` (Pydantic) — **never** raw `os.getenv()` in functions
- **Logging:** Uses `utils.logger.create_logger()` — **never** `print()`
- **File I/O:** Uses `utils.io.atomic_write_json()` for all JSON writes

#### Containerization
Multi-stage Docker build:
```dockerfile
# Stage 1: Build React (Node.js)
FROM node:20-alpine AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --production=false
COPY web/ ./
RUN npm run build

# Stage 2: Production (Python + Static)
FROM python:3.11-slim AS production
COPY --from=frontend-build /app/web/dist /app/static
# ... FastAPI setup
```

### 4.2 Network & Edge (Cloudflare)

| Component | Configuration |
|:---|:---|
| **Tunnel** | `cloudflared` container → `http://storyteller:8000` → `https://straightouttacolington.com` |
| **Access** | Email OTP authentication for allowlisted family members |
| **Caching** | Static assets (JS/CSS) cached at edge; API responses not cached |
| **Security** | JWT in `Cf-Access-Jwt-Assertion` header (optional backend verification) |

### 4.3 Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FastAPI Backend                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ /api/status │  │/api/narrative│  │ /api/riddle │  │ /api/chart│  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │
│         │                │                │                │        │
│         ▼                ▼                ▼                ▼        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ status.json │  │ Narrative   │  │ scorekeeper │  │  chart_   │  │
│  │ (read)      │  │ Manager     │  │ .py         │  │ generator │  │
│  └─────────────┘  │ (cache+lock)│  └─────────────┘  │ (cached)  │  │
│                   └──────┬──────┘                   └───────────┘  │
│                          │                                          │
│                          ▼                                          │
│                   ┌─────────────┐                                   │
│                   │ narrator.   │                                   │
│                   │ generate_   │──► Gemini API                     │
│                   │ narrative_  │    (rate-limited)                 │
│                   │ only()      │                                   │
│                   └─────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Security & Authentication

### 5.1 Cloudflare Access (Zero Trust)

| Aspect | Implementation |
|:---|:---|
| **Method** | One-Time PIN (OTP) via Email |
| **Allowlist** | Configured Access Group (family emails) |
| **Session** | 24-hour session cookie |
| **JWT** | `Cf-Access-Jwt-Assertion` header on every request |

### 5.2 Backend Security

| Concern | Mitigation |
|:---|:---|
| **JWT Verification** | Optional middleware validates Cloudflare JWT signature |
| **Rate Limiting** | FastAPI `slowapi` middleware: 60 req/min per IP |
| **Narrative Regen** | Hard limit: 4/hour globally (file-based counter) |
| **Input Sanitization** | Riddle guesses stripped of HTML/script tags |
| **CORS** | Restrict to `straightouttacolington.com` origin |

### 5.3 User Identification (Riddle Game)

Cloudflare Access JWT contains user email. Backend extracts for scorekeeping:
```python
from jose import jwt

def get_user_email(request: Request) -> str:
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if token:
        claims = jwt.get_unverified_claims(token)
        return claims.get("email", "anonymous")
    return "anonymous"
```

---

## 6. Testing & Resilience Strategy

### 6.1 Current Foundation

The project has established testing infrastructure:
- **Framework:** pytest 7.4+ with coverage, markers, async support
- **Fixtures:** `tests/conftest.py` with sensor data, weather data, file system, mock fixtures
- **Markers:** `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- **Mocking:** `pytest-mock`, `responses` (HTTP), `freezegun` (datetime)

### 6.2 Web Module Testing Strategy

#### Backend Tests (`tests/web/`)

| Test File | Coverage | Approach |
|:---|:---|:---|
| `test_api_status.py` | `/api/status` endpoint | Mock `status.json` reads; verify staleness logic |
| `test_api_narrative.py` | `/api/narrative` endpoint | Mock `NarrativeManager`; verify caching/rate-limiting |
| `test_api_riddle.py` | `/api/riddle/*` endpoints | Reuse existing `scorekeeper` test patterns |
| `test_narrative_manager.py` | `NarrativeManager` class | File locking, cache invalidation, blackout windows |
| `test_websocket.py` | `/ws` endpoint | Async tests with `pytest-asyncio`; mock file watchers |

**Key Fixtures to Add:**
```python
@pytest.fixture
def mock_narrative_cache(tmp_path):
    """Temporary narrative cache for isolation."""
    cache_path = tmp_path / "narrative_cache.json"
    return cache_path

@pytest.fixture
async def test_client():
    """FastAPI test client with async support."""
    from httpx import AsyncClient
    from web.api.main import app
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

#### Frontend Tests (`web/src/__tests__/`)

| Test Type | Tool | Coverage |
|:---|:---|:---|
| **Component** | Vitest + React Testing Library | Render, user interaction |
| **Hook** | Vitest | `useWebSocket`, `useNarrative` |
| **Integration** | Playwright | Full user flows (guarded by CI) |

**Minimal E2E Test (Playwright):**
```typescript
// e2e/dashboard.spec.ts
test('dashboard loads and shows sensor data', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('interior-temp')).toBeVisible();
  await expect(page.getByTestId('narrative-text')).toContainText(/greenhouse|captain/i);
});
```

### 6.3 Test Pyramid

```
        ╱╲
       ╱  ╲       E2E (Playwright)
      ╱────╲      2-3 critical user flows
     ╱      ╲
    ╱────────╲    Integration Tests
   ╱          ╲   API endpoints with mocked deps
  ╱────────────╲
 ╱              ╲ Unit Tests
╱────────────────╲ Pure functions, managers, utilities
```

**Targets:**
- Unit: 80%+ coverage on new `web/` code
- Integration: All API endpoints have at least one happy-path test
- E2E: 2-3 smoke tests (dashboard load, riddle submission, chart render)

### 6.4 Resilience Patterns

| Pattern | Implementation | Test Approach |
|:---|:---|:---|
| **Graceful Degradation** | Fallback narrative on AI failure | Mock Gemini to raise; verify fallback returned |
| **Circuit Breaker** | Rate limit counter resets after window | Use `freezegun` to time-travel; verify counter reset |
| **Atomic Writes** | `utils.io.atomic_write_json()` | Simulate concurrent writes; verify no corruption |
| **WebSocket Reconnect** | Client auto-reconnects with backoff | Mock disconnect; verify reconnect attempts |
| **Stale Data Handling** | `_stale` flags in API response | Set `last_seen` to old timestamp; verify flag |

### 6.5 CI Integration (Future)

```yaml
# .github/workflows/test.yml (scaffold)
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -m "not slow" --cov
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd web && npm ci && npm test
```

### 6.6 Key Testing Principles

1. **Mock at boundaries:** External services (Gemini, Cloudflare, SMTP) are always mocked
2. **Use existing fixtures:** Extend `conftest.py` rather than duplicating
3. **Test behaviors, not implementation:** Verify API contracts, not internal state
4. **Fail fast in dev:** Pre-commit hooks run `pytest -m unit` (~10s)
5. **No flaky tests:** Time-dependent tests use `freezegun`; async tests use proper awaits

---

## 7. UI/UX Design System

**Theme:** "Scientific Dark Mode" — matches existing email CSS.

### 7.1 Color Palette

| Token | Hex | Usage |
|:---|:---|:---|
| `background.default` | `#121212` | Page background |
| `background.paper` | `#1E1E1E` | Cards, surfaces |
| `primary.main` | `#6b9b5a` | Greenhouse Green (Inside/Hero) |
| `secondary.main` | `#60a5fa` | Ocean Blue (Outside/Context) |
| `error.main` | `#d32f2f` | Alerts, critical battery |
| `warning.main` | `#ffa726` | Stale data, low battery |
| `text.primary` | `#f5f5f5` | Main text |
| `text.secondary` | `#a3a3a3` | Muted text, labels |

### 7.2 MUI Theme Configuration

```typescript
// web/src/theme.ts
import { createTheme } from '@mui/material/styles';

export const gazetteTheme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#121212', paper: '#1E1E1E' },
    primary: { main: '#6b9b5a' },
    secondary: { main: '#60a5fa' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", sans-serif',
    h1: { fontSize: '2rem', fontWeight: 700 },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 12, border: '1px solid #2d2d2d' },
      },
    },
  },
});
```

### 7.3 Layout Structure

```
┌─────────────────────────────────────────────┐
│  AppBar: "Straight Outta Colington" + Pulse │
├─────────────────────────────────────────────┤
│  Hero: Webcam Image (swipeable on mobile)   │
├─────────────────────────────────────────────┤
│  Vitals: 2x2 Grid                           │
│  ┌─────────────┐ ┌─────────────┐            │
│  │ Inside Temp │ │ Outside Temp│            │
│  │    68°      │ │    42°      │            │
│  └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐            │
│  │Inside Humid │ │  Battery    │            │
│  │    72%      │ │   3.9V ███  │            │
│  └─────────────┘ └─────────────┘            │
├─────────────────────────────────────────────┤
│  Captain's Log: Narrative Text              │
│  (Auto-refreshed • "Cached" badge if stale) │
├─────────────────────────────────────────────┤
│  Riddle Game: Question + Input + Submit     │
├─────────────────────────────────────────────┤
│  FAB → Opens Bottom Sheet:                  │
│    • Charts (24h/7d/30d toggle)             │
│    • Timelapse Gallery                      │
│    • Leaderboard                            │
└─────────────────────────────────────────────┘
```

---

## 8. API Contract

### 8.1 Sensor Status

```yaml
GET /api/status
Response 200:
  {
    "sensors": {
      "interior_temp": 68.2,
      "interior_humidity": 72.1,
      "exterior_temp": 42.5,
      "exterior_humidity": 85.3,
      "satellite_battery": 3.92,
      "satellite_pressure": 30.12
    },
    "stale": {
      "interior_temp": false,
      "interior_humidity": false,
      "exterior_temp": true,
      "exterior_humidity": true,
      "satellite_battery": false
    },
    "last_seen": {
      "interior_temp": "2026-01-18T16:45:00Z",
      "exterior_temp": "2026-01-18T14:30:00Z"
    },
    "updated_at": "2026-01-18T16:55:00Z"
  }
```

### 8.2 Narrative

```yaml
GET /api/narrative
Response 200:
  {
    "subject": "Cold snap holding steady",
    "headline": "The greenhouse is doing its job overnight",
    "body": "We're sitting at 68° inside while it's...",
    "generated_at": "2026-01-18T15:30:00Z",
    "cached": false,
    "next_refresh_allowed_at": "2026-01-18T16:30:00Z"
  }

POST /api/narrative/refresh
Headers: Cf-Access-Jwt-Assertion: <jwt>
Response 200: (same schema as GET)
Response 429:
  {
    "error": "rate_limited",
    "message": "Narrative refresh limit reached. Try again in 12 minutes.",
    "retry_after": 720
  }
Response 503:
  {
    "error": "generation_in_progress",
    "message": "Another user triggered refresh. Using cached version.",
    "cached_narrative": { ... }
  }
```

### 8.3 Riddle Game

```yaml
GET /api/riddle
Response 200:
  {
    "question": "I cost more than your car, sit in the driveway...",
    "date": "2026-01-18",
    "active": true
  }
Response 404:
  {
    "error": "no_riddle",
    "message": "No riddle available. Check back after the morning Gazette."
  }

POST /api/riddle/guess
Headers: Cf-Access-Jwt-Assertion: <jwt>
Body: { "guess": "a boat" }
Response 200 (correct):
  {
    "correct": true,
    "points": 2,
    "is_first": true,
    "rank": 1,
    "message": "Aye, ye got it, landlubber. First to crack it!"
  }
Response 200 (wrong):
  {
    "correct": false,
    "message": "Not quite, matey. The Captain's seen sharper guesses."
  }
Response 200 (already solved):
  {
    "correct": null,
    "already_solved": true,
    "message": "Ye already cracked this one. Save yer ink for tomorrow."
  }

GET /api/leaderboard
Response 200:
  {
    "season_start": "2026-01-01",
    "players": [
      { "display_name": "josh", "points": 15, "wins": 3 },
      { "display_name": "mom", "points": 12, "wins": 2 }
    ]
  }

GET /api/riddle/stats
Headers: Cf-Access-Jwt-Assertion: <jwt>
Response 200:
  {
    "display_name": "josh",
    "points": 15,
    "wins": 3,
    "rank": 1,
    "last_played": "2026-01-17"
  }
```

### 8.4 Camera & Timelapses

```yaml
GET /api/camera/latest
Response 200: image/jpeg (binary)
Headers:
  Content-Type: image/jpeg
  X-Capture-Time: 2026-01-18T16:30:00Z
  Cache-Control: max-age=300

GET /api/timelapses
Response 200:
  {
    "daily": "/static/timelapses/daily_2026-01-18.gif",
    "weekly": "/static/timelapses/weekly_2026-W03.mp4",
    "monthly": "/static/timelapses/monthly_2025-12.mp4"
  }
```

### 8.5 Historical Charts

```yaml
GET /api/charts/{range}
Path: range = "24h" | "7d" | "30d"
Response 200: image/png (binary)
Headers:
  Content-Type: image/png
  X-Generated-At: 2026-01-18T16:00:00Z
  Cache-Control: max-age=300

GET /api/history?hours=168&resolution=hourly
Response 200:
  {
    "resolution": "hourly",
    "points": [
      {
        "timestamp": "2026-01-11T12:00:00Z",
        "interior_temp": 67.5,
        "exterior_temp": 45.2,
        "interior_humidity": 70.1,
        "exterior_humidity": 82.3
      }
    ]
  }
```

### 8.6 WebSocket

```yaml
WS /ws
# Client → Server
{ "type": "subscribe", "channels": ["sensors", "narrative"] }

# Server → Client (sensors update)
{
  "type": "sensors",
  "data": {
    "interior_temp": 68.3,
    "interior_humidity": 71.8,
    "updated_at": "2026-01-18T17:00:00Z"
  }
}

# Server → Client (narrative update)
{
  "type": "narrative",
  "data": {
    "subject": "...",
    "generated_at": "2026-01-18T17:05:00Z"
  }
}

# Server → Client (connection health)
{ "type": "ping" }
# Client should respond:
{ "type": "pong" }
```

### 8.7 Error Response Schema

All error responses follow a consistent format:

```yaml
{
  "error": "error_code",      # Machine-readable code
  "message": "Human message", # User-friendly description
  "details": {}               # Optional additional context
}
```

---

## 9. Backend Class Designs

### 9.1 NarrativeManager

```python
# scripts/narrative_manager.py
"""Narrative caching and rate-limiting for web API."""

import fcntl
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, Any

from utils.io import atomic_write_json, atomic_read_json
from utils.logger import create_logger
from app.config import settings

log = create_logger("narrative_manager")

CACHE_PATH = "/app/data/narrative_cache.json"
LOCK_PATH = "/app/data/narrative_generation.lock"
RATE_LIMIT_PATH = "/app/data/narrative_rate_limit.json"

MAX_AGE_MINUTES = 60
MAX_GENERATIONS_PER_HOUR = 4
BLACKOUT_BEFORE_EMAIL_MINUTES = 30
EMAIL_HOUR = 7


@dataclass
class CachedNarrative:
    subject: str
    headline: str
    body: str
    generated_at: datetime
    cached: bool = False
    
    def is_stale(self) -> bool:
        age = datetime.utcnow() - self.generated_at
        return age > timedelta(minutes=MAX_AGE_MINUTES)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "headline": self.headline,
            "body": self.body,
            "generated_at": self.generated_at.isoformat() + "Z",
            "cached": self.cached,
        }


class NarrativeManager:
    """Thread-safe narrative cache with rate limiting."""
    
    def __init__(self):
        self._cache: Optional[CachedNarrative] = None
        self._load_cache()
    
    def get_narrative(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get current narrative, regenerating if stale."""
        # Implementation handles:
        # - Cache loading/saving
        # - Rate limit checking
        # - Blackout window enforcement
        # - File-based locking for concurrent requests
        # - Fallback on failure
        pass
```

### 9.2 ChartCache

```python
# scripts/chart_cache.py
"""Cached chart generation for web API."""

import time
from typing import Optional, Dict
from dataclasses import dataclass

from scripts.chart_generator import generate_weather_dashboard
from utils.logger import create_logger

log = create_logger("chart_cache")

CACHE_TTL_SECONDS = 300  # 5 minutes


class ChartCache:
    """In-memory cache for chart images."""
    
    def __init__(self):
        self._cache: Dict[str, tuple[bytes, float]] = {}
    
    def get_chart(self, hours: int) -> Optional[bytes]:
        """Get chart PNG, generating if stale or missing."""
        cache_key = f"{hours}h"
        
        if cache_key in self._cache:
            png_bytes, generated_at = self._cache[cache_key]
            if (time.time() - generated_at) < CACHE_TTL_SECONDS:
                return png_bytes
        
        png_bytes = generate_weather_dashboard(hours=hours)
        if png_bytes:
            self._cache[cache_key] = (png_bytes, time.time())
        
        return png_bytes
```

---

## 10. Sensor Key Reference (The Great Swap)

**CRITICAL:** Physical sensors are mapped inversely in MQTT. This is handled by `configs/registry.json` and `status_daemon.py`. The **web API must use normalized keys only.**

| Canonical Key | Physical Location | MQTT Topic | Notes |
|:---|:---|:---|:---|
| `interior_temp` | Inside greenhouse | `greenhouse/exterior/sensor/temp/state` | Swap! |
| `interior_humidity` | Inside greenhouse | `greenhouse/exterior/sensor/humidity/state` | Swap! |
| `exterior_temp` | Outside (yard) | `greenhouse/satellite-2/sensor/temperature/state` | |
| `exterior_humidity` | Outside (yard) | `greenhouse/satellite-2/sensor/humidity/state` | |
| `satellite_battery` | Solar sensor | `greenhouse/satellite-2/sensor/battery/state` | Voltage (V) |
| `satellite_pressure` | Solar sensor | `greenhouse/satellite-2/sensor/pressure/state` | inHg |

**Rules:**
1. **Never** use MQTT topic names in frontend code
2. **Always** use `interior_*` / `exterior_*` canonical keys
3. Backend normalizes via `registry.json` before serving

---

## 11. Implementation Plan

### Phase 1: Infrastructure & Backend Foundation (Week 1)
1. Create FastAPI app structure (`web/api/`)
2. Implement `/api/status` endpoint with staleness detection
3. Implement `NarrativeManager` with caching and rate limiting
4. Add `narrator.generate_narrative_only()` function
5. Implement riddle endpoints (adapt `scorekeeper.py`)
6. Add backend tests for new endpoints

### Phase 2: Frontend Foundation (Week 2)
1. Initialize React/Vite project with MUI
2. Configure theme (§7 colors)
3. Set up TanStack Query
4. Build dashboard layout skeleton (mobile-first)
5. Implement Vitals module (REQ-A1-A5)

### Phase 3: Core Features (Week 3)
1. Implement Narrative module (REQ-B1-B6)
2. Implement Riddle module (REQ-C1-C5)
3. Add WebSocket support for real-time updates
4. Frontend component tests

### Phase 4: Polish & Deploy (Week 4)
1. Implement Camera/Timelapse module (REQ-D1-D3)
2. Implement Charts module (REQ-E1-E3)
3. Set up Cloudflare Tunnel and Access
4. E2E smoke tests
5. Production deployment

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|:---|:---|:---|
| **Thundering Herd** | Multiple users trigger parallel AI generation | File-lock in `NarrativeManager`; return cached during lock |
| **Gemini Rate Limits** | API errors during high usage | 4/hour hard limit; graceful fallback to cache |
| **Cloudflare Latency** | Slight overhead on every request | Cache static assets at edge; API responses are small |
| **WebSocket Disconnects** | Users miss updates | Auto-reconnect with exponential backoff; fallback to polling |
| **Pi Memory Limits** | Matplotlib/scipy spike during chart gen | Cache charts for 5 mins; generate off-peak |
| **JSONL Query Performance** | 30-day queries slow | Hourly aggregation server-side; see BACK-01 |

---

## 13. Success Metrics

| Metric | Target | Measurement |
|:---|:---|:---|
| **Page Load Time** | <3s on 4G mobile | Lighthouse audit |
| **Sensor Freshness** | <30s latency from MQTT → UI | WebSocket message timestamps |
| **Uptime** | 99.5% | Cloudflare analytics |
| **Narrative Cache Hit Rate** | >80% | Server logs |
| **Riddle Engagement** | 3+ guesses/day | `riddle_daily_log.json` |
| **Test Coverage** | >80% on `web/` code | pytest-cov report |

---

*Document Version: 2.1 • Last Updated: January 18, 2026*
