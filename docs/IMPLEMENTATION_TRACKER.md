# Colington Omniscient Protocol v2.0 — Implementation Tracker

> Last Updated: 2026-01-17
> Status: **COMPLETE** ✅

---

## EPIC 1: Riddle Game Polish
*Goal: Complete the player feedback loop*

### Story 1.1: HELP Command
- **Status:** [x] Complete
- **File:** `scripts/inbox_monitor.py`
- **Description:** Add HELP command that returns game instructions
- **Acceptance Criteria:**
  - [x] Email "HELP" to bot → receive formatted instructions
  - [x] Rate limiting applies (max 5 replies/day)
- **Estimate:** 10 min

### Story 1.2: STATS Command  
- **Status:** [x] Complete
- **File:** `scripts/inbox_monitor.py`
- **Description:** Add STATS command that returns player's personal stats
- **Acceptance Criteria:**
  - [x] Email "STATS" to bot → receive points, wins, rank
  - [x] New players get "haven't played yet" message
- **Estimate:** 10 min

### Story 1.3: Rain Data in Weather Service
- **Status:** [x] Complete
- **File:** `scripts/weather_service.py`
- **Description:** Add `rain_last_24h_in` to weather data for septic logic
- **Acceptance Criteria:**
  - [x] `get_current_weather()` returns `rain_last_24h_in` key
  - [x] Value is in inches (converted from mm)
- **Estimate:** 5 min

---

## EPIC 2: Knowledge Graph + Context Engine
*Goal: Add situational awareness to narratives*

### Story 2.1: Create Knowledge Graph JSON
- **Status:** [x] Complete
- **File:** `data/colington_knowledge_graph.json`
- **Description:** Create trimmed JSON with thresholds, micro-seasons, sensory triggers
- **Acceptance Criteria:**
  - [x] File parses without error
  - [x] All items have `id` and `priority` fields
  - [x] Triggers match available data sources
- **Estimate:** 15 min

### Story 2.2: Create Context Engine
- **Status:** [x] Complete
- **File:** `scripts/context_engine.py`
- **Description:** Implement trigger evaluation for all trigger types
- **Acceptance Criteria:**
  - [x] `get_rich_context()` evaluates month, date, wind, rain triggers
  - [x] Returns prioritized list of flags (max 5)
  - [x] Handles missing data gracefully
  - [x] `get_random_riddle_topic()` integrates with existing history
- **Estimate:** 30 min

### Story 2.3: Integrate Context Engine into Narrator
- **Status:** [x] Complete
- **File:** `scripts/narrator.py`
- **Description:** Inject context flags into build_prompt()
- **Acceptance Criteria:**
  - [x] Flags appear in "LOCAL INTELLIGENCE" section
  - [x] Critical flags appear first
  - [x] Failure is non-fatal (graceful degradation)
- **Estimate:** 10 min

### Story 2.4: Add Config Path
- **Status:** [x] Complete
- **File:** `app/config.py`
- **Description:** Add `knowledge_graph_path` and `prompts_dir` to Settings
- **Acceptance Criteria:**
  - [x] Path configurable via environment variable
  - [x] Default is `/app/data/colington_knowledge_graph.json`
- **Estimate:** 5 min

---

## EPIC 3: Hot-Reload Prompts
*Goal: Tune narrative voice without container rebuilds*

### Story 3.1: Create Prompts Directory and Persona File
- **Status:** [x] Complete
- **File:** `data/prompts/narrator_persona.txt`
- **Description:** Extract persona section from build_prompt()
- **Acceptance Criteria:**
  - [x] File contains persona/voice instructions
  - [x] No code, just text instructions
- **Estimate:** 5 min

### Story 3.2: Add Prompt Loader
- **Status:** [x] Complete
- **File:** `scripts/narrator.py`
- **Description:** Add `_load_prompt_template()` function
- **Acceptance Criteria:**
  - [x] Loads from disk on each call (no caching)
  - [x] Falls back to hardcoded default if file missing
  - [x] Logs warning on fallback
- **Estimate:** 5 min

### Story 3.3: Update Docker Compose
- **Status:** [x] Complete (N/A)
- **File:** `docker-compose.yml`
- **Description:** Add volume mount for prompts directory
- **Acceptance Criteria:**
  - [x] Already covered by existing `./data:/app/data` mount
  - [x] Container can read files from host
- **Estimate:** 2 min

### Story 3.4: Integration Test
- **Status:** [x] Complete
- **Description:** Verify hot-reload works end-to-end
- **Acceptance Criteria:**
  - [x] Edit persona file → next email reflects change
  - [x] No container restart required
- **Estimate:** 5 min

---

## Verification Commands

```bash
# Test rain data
docker exec -it greenhouse-storyteller python -c "
import weather_service
d = weather_service.get_current_weather()
print('Rain (in):', d.get('rain_last_24h_in', 'MISSING'))
"

# Test context engine  
docker exec -it greenhouse-storyteller python -c "
from datetime import datetime
import context_engine
flags = context_engine.get_rich_context(
    datetime.now(),
    {'wind_mph': 5, 'wind_deg': 270, 'outdoor_temp': 65, 'rain_last_24h_in': 0},
    {'observed_level_ft': 1.0}
)
for f in flags: print(f)
"

# Test prompt hot-reload
docker exec -it greenhouse-storyteller python -c "
import narrator
print(narrator._load_prompt_template('narrator_persona.txt')[:100])
"

# Test HELP command (manual)
# Send email with subject "HELP" to bot address

# Test STATS command (manual)
# Send email with subject "STATS" to bot address
```

---

## Architecture Notes

### Knowledge Graph Design Decisions
- **Trimmed JSON:** Removed unused `zones`, `local_institutions`, `facebook_gossip`
- **Priority System:** All items have priority field (critical > warning > flavor)
- **Integration:** riddle_topics integrates with existing riddle_history.json deduplication

### Layered Intelligence
```
Layer 0: Raw Data (wind_mph, temp, sound_level)
    ↓
Layer 1: Computed Alerts (FLOODING, BRIDGE_ADVISORY) 
    ↓
Layer 2: Situational Flavor (Locals Summer, peat smoke)
    ↓
Layer 3: AI Synthesis (natural prose)
```

### What Stays in Prompt vs Moves to KG
- **KEEP in prompt:** Persona, voice, formatting rules (AI instructions)
- **MOVE to KG:** Thresholds, seasonal context, local landmarks (facts)

---

## Session Log

### 2026-01-17 Session
- [x] Created implementation tracker
- [x] Story 1.1: HELP command
- [x] Story 1.2: STATS command
- [x] Story 1.3: Rain data
- [x] Story 2.1: Knowledge graph JSON
- [x] Story 2.2: Context engine
- [x] Story 2.3: Narrator integration
- [x] Story 2.4: Config path
- [x] Story 3.1: Persona file
- [x] Story 3.2: Prompt loader
- [x] Story 3.3: Docker compose (already covered by ./data:/app/data mount)
- [x] Story 3.4: Integration test
- [x] Verified context engine locally - all test cases pass
- [x] Deployed and tested (email sent to 6 recipients)
- [x] Context engine produced 2 flags in production run
