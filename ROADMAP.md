# Greenhouse Gazette - Roadmap

> Status as of January 5, 2026

---

## ✅ Completed (Audit Phases 0-3 + Extensions)

### Phase 0: Safety Rails
- [x] Snapshot tests for `build_email()` output
- [x] Golden master HTML fixture
- [x] Mock sensor data fixture

### Phase 1: Jinja2 Extraction
- [x] Extract ~800 lines of HTML to templates
- [x] Create template structure:
  - `templates/base.html`
  - `templates/daily_email.html` (handles both daily and Sunday "Weekly Edition")
  - `templates/components/sensor_card.html`
  - `templates/components/weather_details.html`
  - `templates/components/riddle_card.html`
  - `templates/components/alert_banner.html`
  - `templates/styles/email.css`
- [x] Extract `email_sender.py` (SMTP logic)
- [x] Create `email_templates.py` (Jinja2 rendering)
- [x] Feature flag: `USE_TEMPLATES` removed (templates mandatory)

### Phase 2: Config Migration (All Docker Scripts)
- [x] `publisher.py` → `app.config.settings`
- [x] `email_sender.py` → `app.config.settings`
- [x] `status_daemon.py` → `app.config.settings`
- [x] `device_monitor.py` → `app.config.settings`
- [x] `narrator.py` → `app.config.settings` + atomic JSON
- [x] `weather_service.py` → `app.config.settings`
- [x] `coast_sky_service.py` → `app.config.settings`
- [x] `timelapse.py` → `app.config.settings`
- [x] `extended_timelapse.py` → `app.config.settings`
- [x] `broadcast_email.py` → `app.config.settings`
- [x] `weekly_digest.py` → `app.config.settings`
- [x] `ingestion.py` → `app.config.settings`

### Phase 3: Cleanup & Tooling
- [x] Email preview server (`scripts/email_preview.py`)
- [x] Add `email-preview` service to docker-compose
- [x] Document sensor remapping in `scripts/README.md`
- [x] Mark inline HTML as deprecated
- [x] Templates enabled by default

---

## 🔄 Deferred (Lower Priority)

### SensorSnapshot Integration
**Status:** Deferred due to behavioral difference

The `app/models.py` `SensorSnapshot.from_status_dict()` has different stale-checking behavior than `publisher.py`:
- **Model:** Missing timestamp = stale (strict)
- **Publisher:** Missing timestamp = fresh (lenient)

Integrating would risk regression. Requires:
1. Decide on correct behavior
2. Update model or publisher to match
3. Add tests for edge cases

### Remote Node Scripts
**Status:** Skipped (run outside Docker)

These scripts run on the remote Pi, not in Docker containers, so they don't have access to `app.config`:
- `camera_mqtt_bridge.py` (8 os.getenv calls)
- `ha_sensor_bridge.py` (6 os.getenv calls)

### Delete Inline HTML from Publisher
**Status:** ✅ COMPLETED (Jan 5, 2026)

- Removed ~500 lines of deprecated inline HTML from `publisher.py`
- Removed dead helper functions: `build_debug_footer`, `build_riddle_card`, `build_alert_banner`, `build_broadcast_card`
- Removed `USE_TEMPLATES` feature flag (templates now mandatory)
- Publisher reduced from 1,398 to 895 lines (-36%)

---

## 📋 Future Enhancements (Nice to Have)

| Feature | Effort | Notes |
|---------|--------|-------|
| Type hints for `publisher.py` | 4h | Would improve IDE support |
| CSS inlining at build time | 2h | Use `premailer` or `css_inline` |
| Template preview in CI | 2h | Render + screenshot comparison |
| Email A/B testing | 4h | Feature flag different templates |

---

## 🏆 Metrics

### Before Audit (Jan 5, 2026)
- Health Score: **C+ (72/100)**
- `publisher.py`: 1,330 lines
- `os.getenv()` calls: 110 across 18 scripts
- Template system: None

### After Audit (Jan 5, 2026)
- Health Score: **B+ (estimated)**
- `publisher.py`: Still large but templates extract rendering
- Config migrated: 4 high-priority scripts
- Template system: 9 files, hot-reload preview server
- Inline HTML: Deprecated, templates default

---

*Last updated: January 5, 2026*
