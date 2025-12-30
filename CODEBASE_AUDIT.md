# Greenhouse Gazette Codebase Audit

**Date:** December 30, 2024  
**Scope:** Production stability-focused bloat reduction and maintainability improvements

---

## Executive Summary

This audit identifies **4 high-priority issues** and **12 moderate-priority opportunities** for reducing bloat and improving maintainability. The codebase is functional but has accumulated technical debt primarily in the form of code duplication and oversized files.

**Key Metrics:**
- Total Python files in `/scripts`: 21
- Lines of code: ~8,000
- Files >300 lines: 9 (43%)
- Duplicate functions identified: 21+ `log()` functions, 2 `sample_frames_evenly()`, 9 atomic write patterns

---

## 1. Dead Code & Leftovers

### 🔴 CRITICAL: Exact Duplicate File

| File | Lines | Issue |
|------|-------|-------|
| `scripts/publisher_beta.py` | 1,332 | **100% identical to `publisher.py`** |

**Evidence:** `diff publisher.py publisher_beta.py` produces no output.

**Recommendation:** Delete `publisher_beta.py` immediately. This is zero-risk removal.

**Risk Level:** 🟢 LOW - Safe to delete, no references found.

---

### 🟡 MODERATE: Redundant Internal Imports

| File | Line(s) | Issue |
|------|---------|-------|
| `scripts/narrator.py` | 34, 438, 650 | `import re` repeated inside functions when already imported at line 3 |

```python
# Line 3 (top-level - correct)
import re

# Line 34 (inside function - redundant)
        import re
        pattern = re.compile(...)
```

**Recommendation:** Remove the 3 redundant `import re` statements inside functions.

**Risk Level:** 🟢 LOW - No behavioral change.

---

### 🟡 MODERATE: Unused App Layer Models

| File | Status |
|------|--------|
| `app/models.py` (286 lines) | Contains `SensorSnapshot`, `WeatherData` models that **duplicate** logic in `publisher.py` but are not imported anywhere in production |
| `app/services/vitals_formatter.py` (225 lines) | Contains `VitalsFormatter` class that duplicates `fmt_*` functions from `publisher.py` but is not imported |
| `app/config.py` (231 lines) | Pydantic Settings class not used by any script in `/scripts` |

**Evidence:** No imports found in `/scripts/*.py` for these modules.

**Recommendation:** Either:
1. **Delete** these files if they were exploratory/planned refactors never completed
2. **Or migrate** publisher.py to use them (larger effort, see Section 3)

**Risk Level:** 🟡 MEDIUM - Need to confirm these aren't used by external systems (e.g., future API).

---

### 🟢 LOW: Empty/Minimal Files

| File | Issue |
|------|-------|
| `scripts/.gitkeep` | Empty file, can be removed if directory has content |
| `scripts/__init__.py` | Empty file, may be needed for imports |

---

## 2. Duplication

### 🔴 CRITICAL: 21 Identical `log()` Functions

Every script in `/scripts` has its own copy of the same logging function:

```python
def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [{MODULE_NAME}] {message}", flush=True)
```

**Files affected:** `publisher.py`, `narrator.py`, `chart_generator.py`, `status_daemon.py`, `timelapse.py`, `extended_timelapse.py`, `coast_sky_service.py`, `device_monitor.py`, `camera_mqtt_bridge.py`, `weather_service.py`, `ha_sensor_bridge.py`, `golden_hour.py`, `broadcast_email.py`, `web_server.py`, `ingestion.py`, `scheduler.py`, `curator.py`, `stats.py`, `weekly_digest.py`, `publisher_beta.py`

**Recommendation:** Create `scripts/utils/logger.py`:

```python
from datetime import datetime

def create_logger(module_name: str):
    def log(message: str) -> None:
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[{ts}] [{module_name}] {message}", flush=True)
    return log
```

**Risk Level:** 🟢 LOW - Mechanical refactor with no behavior change. Can be done incrementally.

---

### 🟡 MODERATE: Duplicate `sample_frames_evenly()` Function

| File | Lines |
|------|-------|
| `scripts/timelapse.py` | 146-158 |
| `scripts/extended_timelapse.py` | 76-86 |

Both implementations are identical.

**Recommendation:** Extract to shared module (e.g., `scripts/utils/image_utils.py`).

**Risk Level:** 🟢 LOW - Mechanical refactor.

---

### 🟡 MODERATE: Duplicate Email Sending Logic

SMTP connection and sending code is duplicated in 4 files:

| File | Function |
|------|----------|
| `scripts/publisher.py` | `send_email()` |
| `scripts/publisher_beta.py` | `send_email()` (duplicate file) |
| `scripts/device_monitor.py` | `_send_alert_email()` |
| `scripts/extended_timelapse.py` | Inline SMTP code |

**Recommendation:** Create `scripts/utils/email.py` with a shared `send_email()` function.

**Risk Level:** 🟡 MEDIUM - Email is critical path. Requires careful testing.

---

### 🟡 MODERATE: Duplicate Atomic Write Pattern

The "write to temp, fsync, replace" pattern is repeated 9 times:

```python
tmp_path = f"{path}.tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(data, f)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_path, path)
```

**Files:** `narrator.py` (2x), `status_daemon.py` (3x), `device_monitor.py` (2x), `coast_sky_service.py` (1x)

**Recommendation:** Create `scripts/utils/io.py`:

```python
def atomic_write_json(path: str, data: Any, indent: int = 2) -> None:
    """Write JSON atomically to protect against corruption."""
    tmp_path = f"{path}.tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
```

**Risk Level:** 🟢 LOW - SD card write protection is critical; shared function actually improves consistency.

---

### 🟡 MODERATE: Duplicate Formatting Functions

`app/services/vitals_formatter.py` duplicates functions defined inline in `publisher.py`:
- `fmt()`, `fmt_battery()`, `fmt_temp_high_low()`, `fmt_temp_range()`, `fmt_time()`, `fmt_wind()`, `fmt_moon_phase()`, `get_condition_emoji()`

**Current state:** `publisher.py` defines these as nested functions inside `build_email()` (lines 431-540). `VitalsFormatter` class exists but isn't used.

**Recommendation:** Migrate `publisher.py` to use `VitalsFormatter` class, then delete the nested functions.

**Risk Level:** 🟡 MEDIUM - Affects email output; needs visual QA.

---

## 3. Modularization (SRP Violations)

### 🔴 CRITICAL: `publisher.py` - 1,332 Lines

This file does too much:
1. **Data loading** - `load_latest_sensor_snapshot()`
2. **Staleness checking** - `check_stale_data()`
3. **Sensor remapping** - lines 160-210
4. **Formatting** - 9 `fmt_*` functions (lines 431-540)
5. **HTML templating** - `build_email()` contains ~500 lines of inline HTML
6. **Email sending** - `send_email()`
7. **CLI handling** - `__main__` block

**Suggested Breakdown:**

| New Module | Responsibility | Est. Lines |
|------------|---------------|------------|
| `publisher.py` | Orchestration only | ~100 |
| `email_builder.py` | HTML template generation | ~400 |
| `sensor_loader.py` | Data loading + remapping | ~150 |
| `utils/formatters.py` | All fmt_* functions | ~150 |
| `utils/email.py` | SMTP sending | ~50 |

**Risk Level:** 🔴 HIGH - This is a major refactor affecting the critical daily email path. Recommend phased approach:
1. First extract `utils/` modules (low risk)
2. Then extract `email_builder.py` (medium risk)
3. Finally slim down `publisher.py` (high risk)

---

### 🟡 MODERATE: `narrator.py` - 721 Lines

Mixes concerns:
1. **Prompt building** - `build_prompt()` (~100 lines)
2. **AI client management** - `_get_client()`
3. **Response parsing** - scattered parsing logic
4. **Riddle state management** - `_load_riddle_state()`, `_save_riddle_state()`, `_generate_joke_or_riddle_paragraph()`
5. **History management** - `_load_history()`, `_save_history()`
6. **Main generation** - `generate_update()`

**Suggested Breakdown:**

| New Module | Responsibility |
|------------|---------------|
| `narrator.py` | Main generation logic |
| `riddle_manager.py` | Riddle state and generation |
| `narrative_history.py` | History persistence |

**Risk Level:** 🟡 MEDIUM - AI generation is critical but has fallbacks.

---

### 🟡 MODERATE: `chart_generator.py` - 718 Lines

Better structured than others, but could split:
- Data loading (`_load_sensor_data`, `_extract_series`) → `chart_data.py`
- Rendering logic stays in `chart_generator.py`

**Risk Level:** 🟢 LOW - Already has good lazy loading patterns.

---

### 🟡 MODERATE: Other Large Files

| File | Lines | Notes |
|------|-------|-------|
| `status_daemon.py` | 502 | Could extract stats calculation |
| `coast_sky_service.py` | 440 | Acceptable for a service module |
| `extended_timelapse.py` | 430 | Could share code with `timelapse.py` |
| `device_monitor.py` | 391 | Reasonable for its scope |
| `camera_mqtt_bridge.py` | 365 | Acceptable |
| `timelapse.py` | 361 | Could share code with `extended_timelapse.py` |

---

## 4. Performance Risks

### 🟡 MODERATE: Recursive Glob on Archive

```python
# publisher.py lines 44-48
pattern_jpg = os.path.join(ARCHIVE_ROOT, "**", "*.jpg")
candidates = glob.glob(pattern_jpg, recursive=True)
```

**Issue:** As the archive grows (potentially thousands of images), this becomes increasingly slow.

**Current mitigation:** Only used when timelapse creation fails.

**Recommendation:** Consider caching or limiting to recent date directories:

```python
# Only search last 7 days instead of entire archive
recent_dirs = [get_archive_path(days_ago=i) for i in range(7)]
```

**Risk Level:** 🟢 LOW - Fallback path only; not blocking.

---

### 🟡 MODERATE: Sequential API Calls

In `narrator.py` `generate_update()`:

```python
weather = weather_service.get_current_weather()  # HTTP call 1
coast_sky = coast_sky_service.get_coast_sky_summary()  # HTTP call 2
```

**Issue:** These are called sequentially. Each has network latency.

**Current mitigation:** Both have caching (TTL-based).

**Recommendation:** Use `concurrent.futures.ThreadPoolExecutor` for parallel fetching when cache is cold:

```python
with ThreadPoolExecutor(max_workers=2) as executor:
    weather_future = executor.submit(weather_service.get_current_weather)
    coast_sky_future = executor.submit(coast_sky_service.get_coast_sky_summary)
    weather = weather_future.result()
    coast_sky = coast_sky_future.result()
```

**Risk Level:** 🟢 LOW - Caching already mitigates most latency.

---

### 🟢 LOW: Memory Usage in Timelapse

`timelapse.py` loads all selected images into memory for GIF creation. With 50 frames at 600x400, this is ~36MB - acceptable for Pi 5.

**Current mitigation:** `max_frames=50` limit already in place.

**Risk Level:** 🟢 LOW - Already bounded.

---

### 🟢 POSITIVE: Good Patterns Observed

1. **Lazy imports in `chart_generator.py`** - matplotlib/numpy loaded on demand
2. **Resampling for weekly charts** - >48h data resampled to hourly
3. **Bounded buffers** - `MAX_SENSOR_LOG_BUFFER = 1000` prevents OOM
4. **Atomic writes** - fsync + replace pattern protects SD card

---

## Recommended Action Plan

### Phase 1: Zero-Risk Cleanup ✅ COMPLETED (Dec 30, 2024)

| Priority | Action | Risk | Status |
|----------|--------|------|--------|
| 1 | Delete `publisher_beta.py` | 🟢 None | ✅ Done |
| 2 | Remove redundant `import re` in `narrator.py` | 🟢 None | ✅ Done |
| 3 | Create `scripts/utils/logger.py`, migrate 1-2 files as test | 🟢 None | ✅ Done |

### Phase 2: Low-Risk Consolidation ✅ COMPLETED (Dec 30, 2024)

| Priority | Action | Risk | Status |
|----------|--------|------|--------|
| 4 | Create `scripts/utils/io.py` with `atomic_write_json()` | 🟢 Low | ✅ Done |
| 5 | Extract `sample_frames_evenly()` to shared module | 🟢 Low | ✅ Done |
| 6 | Migrate all scripts to shared logger | 🟢 Low | ✅ Done |
| 7 | Migrate atomic write patterns to shared function | 🟢 Low | ✅ Done |

### Phase 3: Medium-Risk Refactors (Future Work)

| Priority | Action | Risk | Effort |
|----------|--------|------|--------|
| 8 | Create `scripts/utils/email.py`, consolidate email sending | 🟡 Medium | 2 hr |
| 9 | Extract `riddle_manager.py` from `narrator.py` | 🟡 Medium | 2 hr |
| 10 | Migrate `publisher.py` to use `VitalsFormatter` | 🟡 Medium | 3 hr |

### Phase 4: Major Refactors (Future Work)

| Priority | Action | Risk | Effort |
|----------|--------|------|--------|
| 11 | Extract `email_builder.py` from `publisher.py` | 🔴 High | 4+ hr |
| 12 | Delete or integrate `app/` layer modules | 🟡 Medium | 2 hr |
| 13 | Consolidate `timelapse.py` + `extended_timelapse.py` | 🟡 Medium | 3 hr |

---

## Summary

The codebase has **good production patterns** (atomic writes, bounded buffers, lazy loading) but has accumulated duplication as features were added.

### Completed (Dec 30, 2024)

- ✅ Deleted `publisher_beta.py` (1,332 lines removed)
- ✅ Removed 3 redundant `import re` statements in `narrator.py`
- ✅ Created `scripts/utils/` package with shared utilities:
  - `logger.py` - Centralized logging (`create_logger()`)
  - `io.py` - Atomic file I/O (`atomic_write_json()`, `atomic_read_json()`)
  - `image_utils.py` - Image processing (`sample_frames_evenly()`)
- ✅ Migrated all 19 scripts to use shared logger
- ✅ Migrated 9 atomic write patterns to shared function
- ✅ Removed duplicate `sample_frames_evenly()` from `timelapse.py` and `extended_timelapse.py`

**Lines removed:** ~1,400 (duplicate code eliminated)
**New shared code:** ~150 lines in `scripts/utils/`
**Net reduction:** ~1,250 lines

### Remaining (Future Work)

- Phase 3: Email consolidation, riddle extraction, VitalsFormatter migration
- Phase 4: Major publisher.py refactor, app/ layer cleanup
