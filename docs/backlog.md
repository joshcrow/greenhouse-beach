# Greenhouse Gazette Web — Backlog

**Last Updated:** January 18, 2026

This document tracks future enhancements and deferred work items for the SOC web dashboard project.

---

## Priority Levels

| Level | Definition |
|:---|:---|
| **P1** | Critical for v2.0 but deferred from initial release |
| **P2** | High value, implement after stable v1 |
| **P3** | Nice-to-have, opportunistic |

---

## Backlog Items

### BACK-01: SQLite for Historical Sensor Data
**Priority:** P2  
**Effort:** Medium (2-3 days)  
**Category:** Performance

**Problem:** Current JSONL sensor logs require scanning entire files for range queries. 30-day queries are slow.

**Solution:**
- Create SQLite database at `/app/data/sensors.db`
- Schema: `CREATE TABLE readings (timestamp TEXT, key TEXT, value REAL, PRIMARY KEY (timestamp, key))`
- Add migration script to backfill from existing JSONL
- Update `chart_generator.py` to query SQLite for historical data
- Keep JSONL as write buffer; batch insert to SQLite hourly

**Acceptance Criteria:**
- [ ] 30-day chart generation <500ms
- [ ] No data loss during migration
- [ ] JSONL continues to work as fallback

---

### BACK-02: Figma MCP → Windsurf Pipeline
**Priority:** P3  
**Effort:** Large (1-2 weeks)  
**Category:** Developer Experience

**Problem:** Manual translation from Figma designs to React/MUI components.

**Solution:**
- Set up Figma MCP server integration
- Map Figma design tokens to MUI theme variables
- Create component generation templates
- Establish workflow: Figma → MCP → Windsurf → Code

**Dependencies:**
- Stable v1 web dashboard
- Figma MUI Design Kit license
- MCP server infrastructure

**Notes:**
- Josh is a UX designer; this pipeline would accelerate iteration
- Consider starting with simple token sync before full component generation

---

### BACK-03: PWA Offline Support
**Priority:** P3  
**Effort:** Medium (2-3 days)  
**Category:** UX

**Problem:** Dashboard requires connectivity; no graceful offline experience.

**Solution:**
- Add service worker with Workbox
- Cache last-known sensor state
- Show "Last updated X minutes ago" when offline
- Queue riddle guesses for submission when back online

**Acceptance Criteria:**
- [ ] Dashboard displays cached data when offline
- [ ] Clear visual indicator of offline state
- [ ] Riddle guesses submitted once reconnected

---

### BACK-04: Push Notifications (Frost Alerts)
**Priority:** P2  
**Effort:** Medium (3-4 days)  
**Category:** Feature

**Problem:** Captain needs to know about frost risk even when not checking dashboard.

**Solution:**
- Web Push API integration
- Backend trigger when `interior_temp < 40°F` or `exterior_temp < 35°F`
- User opt-in via dashboard settings
- Rate limit: max 1 notification per hour per condition

**Dependencies:**
- PWA service worker (BACK-03)

**Acceptance Criteria:**
- [ ] Notification received on mobile within 5 min of frost condition
- [ ] User can disable notifications
- [ ] No duplicate notifications for same event

---

### BACK-05: Admin Panel
**Priority:** P3  
**Effort:** Large (1 week)  
**Category:** Feature

**Problem:** Captain has no visibility into system health or manual controls via web.

**Solution:**
- Protected `/admin` route (additional Cloudflare Access policy)
- Views: system logs, MQTT connection status, email queue
- Actions: trigger manual email, clear narrative cache, force chart regeneration

**Acceptance Criteria:**
- [ ] Only Captain email can access admin panel
- [ ] View last 100 log entries
- [ ] Manual email trigger works

---

### BACK-06: Interactive Frontend Charts (Recharts)
**Priority:** P2  
**Effort:** Medium (2-3 days)  
**Category:** UX

**Problem:** Current charts are server-rendered PNGs; no interactivity.

**Solution:**
- Replace PNG charts with Recharts components
- Add hover tooltips showing exact values
- Enable zoom/pan on touch devices
- Keep PNG fallback for email embedding

**Dependencies:**
- `/api/history` endpoint returning JSON data points

**Acceptance Criteria:**
- [ ] Touch-friendly chart interactions on mobile
- [ ] Tooltips show timestamp and value on hover
- [ ] Performance: render 168 data points in <100ms

---

### BACK-07: Riddle Hints System
**Priority:** P3  
**Effort:** Small (1 day)  
**Category:** Feature

**Problem:** Some riddles are too hard; users give up.

**Solution:**
- Add optional hint button (costs 1 point to use)
- AI generates hint on demand (rate limited)
- Track hint usage in daily log

**Acceptance Criteria:**
- [ ] Hint button visible after 2 wrong guesses
- [ ] Point deduction recorded in scorekeeper
- [ ] Max 1 hint per riddle per user

---

### BACK-08: Dark/Light Theme Toggle
**Priority:** P3  
**Effort:** Small (1 day)  
**Category:** UX

**Problem:** Some users prefer light mode, especially outdoors.

**Solution:**
- Add theme toggle in app bar
- Persist preference in localStorage
- Respect `prefers-color-scheme` on first visit

**Acceptance Criteria:**
- [ ] Theme persists across sessions
- [ ] All components render correctly in both modes
- [ ] Email CSS unchanged (dark only)

---

### BACK-09: CI/CD Pipeline
**Priority:** P1  
**Effort:** Medium (2 days)  
**Category:** Infrastructure

**Problem:** No automated testing or deployment; manual process error-prone.

**Solution:**
- GitHub Actions workflow for tests on PR
- Auto-deploy to Pi on merge to `main` (via SSH or webhook)
- Slack/Discord notification on deploy

**Acceptance Criteria:**
- [ ] PRs blocked if tests fail
- [ ] Deploy to production within 5 min of merge
- [ ] Rollback mechanism documented

---

### BACK-10: Rate Limit Dashboard
**Priority:** P3  
**Effort:** Small (1 day)  
**Category:** Observability

**Problem:** No visibility into how close we are to API rate limits.

**Solution:**
- Track Gemini API calls in `/app/data/api_usage.json`
- Display usage in admin panel (BACK-05)
- Alert when approaching limits

**Dependencies:**
- Admin Panel (BACK-05)

---

## Completed Items

*Move items here when done, with completion date.*

| ID | Description | Completed |
|:---|:---|:---|
| — | — | — |

---

## Notes

- Items may be re-prioritized based on user feedback after v1 launch
- Large items should be broken into smaller tasks when work begins
- All backlog work should include tests per §6 of PRD
