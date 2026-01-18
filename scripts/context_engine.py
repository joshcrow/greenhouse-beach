"""Context Engine for Colington Omniscient Protocol.

Evaluates the Knowledge Graph against current conditions to produce
prioritized intelligence flags for narrative injection.

Usage:
    from context_engine import get_rich_context, get_random_riddle_topic
    
    flags = get_rich_context(
        date_obj=datetime.now(),
        weather_data={'wind_mph': 25, 'wind_deg': 220, 'rain_last_24h_in': 0},
        coast_data={'observed_level_ft': 2.5}
    )
    # Returns: ['⚠️ Rising water...', '📅 SEASON: Locals Summer...']
"""

import json
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger import create_logger

log = create_logger("context_engine")

# Lazy settings loader
_settings = None

def _get_settings():
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings


# Path configuration
def _get_graph_path() -> str:
    cfg = _get_settings()
    if cfg and hasattr(cfg, 'knowledge_graph_path'):
        return cfg.knowledge_graph_path
    return os.getenv("KNOWLEDGE_GRAPH_PATH", "/app/data/colington_knowledge_graph.json")


_graph_cache: Optional[Dict[str, Any]] = None
_graph_cache_mtime: float = 0


def _load_graph() -> Dict[str, Any]:
    """Load knowledge graph with file modification caching."""
    global _graph_cache, _graph_cache_mtime
    
    path = _get_graph_path()
    
    # Try container path first, then local dev path
    if not os.path.exists(path):
        local_path = os.path.join(os.path.dirname(__file__), '../data/colington_knowledge_graph.json')
        if os.path.exists(local_path):
            path = local_path
        else:
            log(f"Knowledge graph not found at {path}")
            return {}
    
    try:
        mtime = os.path.getmtime(path)
        if _graph_cache is not None and mtime == _graph_cache_mtime:
            return _graph_cache
        
        with open(path, 'r', encoding='utf-8') as f:
            _graph_cache = json.load(f)
            _graph_cache_mtime = mtime
            log(f"Loaded knowledge graph v{_graph_cache.get('version', '?')}")
            return _graph_cache
    except Exception as exc:
        log(f"Error loading knowledge graph: {exc}")
        return {}


def _wind_dir_from_deg(deg: float) -> str:
    """Convert wind degrees to cardinal direction."""
    if deg is None:
        return ""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((deg % 360) / 45.0 + 0.5) % 8
    return dirs[idx]


def _is_wind_direction(deg: float, target_dir: str) -> bool:
    """Check if wind is from a general direction (allows 45° tolerance)."""
    if deg is None:
        return False
    
    actual_dir = _wind_dir_from_deg(deg)
    target_dir = target_dir.upper()
    
    # Direct match
    if actual_dir == target_dir:
        return True
    
    # Allow adjacent directions for broader matching
    # E.g., "W" matches W, SW, NW
    direction_groups = {
        "N": ["N", "NNE", "NNW"],
        "S": ["S", "SSE", "SSW"],
        "E": ["E", "ENE", "ESE"],
        "W": ["W", "WNW", "WSW"],
        "NE": ["NE", "N", "E"],
        "SE": ["SE", "S", "E"],
        "SW": ["SW", "S", "W"],
        "NW": ["NW", "N", "W"],
    }
    
    return actual_dir in direction_groups.get(target_dir, [target_dir])


def _evaluate_triggers(triggers: Dict[str, Any], weather: Dict, coast: Dict, now: datetime) -> bool:
    """Evaluate all triggers in a trigger block. All must pass (AND logic)."""
    if not triggers:
        return True
    
    wind_mph = weather.get('wind_mph') or 0
    wind_deg = weather.get('wind_deg')
    rain_in = weather.get('rain_last_24h_in') or 0
    sound_ft = coast.get('observed_level_ft') or 0
    # Use outdoor_temp if available, fall back to exterior_temp (from sensors)
    temp_f = weather.get('outdoor_temp') or weather.get('exterior_temp') or weather.get('low_temp')
    hour = now.hour
    
    for key, value in triggers.items():
        if key == "temp_gt_f":
            if temp_f is None or temp_f <= value:
                return False
        elif key == "temp_lt_f":
            if temp_f is None or temp_f >= value:
                return False
        elif key == "wind_gt_mph":
            if wind_mph <= value:
                return False
        elif key == "wind_lt_mph":
            if wind_mph >= value:
                return False
        elif key == "wind_dir":
            if not _is_wind_direction(wind_deg, value):
                return False
        elif key == "rain_24h_gt_in":
            if rain_in <= value:
                return False
        elif key == "rain_24h_lt_in":
            if rain_in >= value:
                return False
        elif key == "sound_gt_ft":
            if sound_ft <= value:
                return False
        elif key == "sound_lt_ft":
            if sound_ft >= value:
                return False
        elif key == "hour_between":
            start_hour, end_hour = value
            if not (start_hour <= hour <= end_hour):
                return False
    
    return True


def _check_date_range(item: Dict, now: datetime) -> bool:
    """Check if current date falls within item's date constraints."""
    month = now.month
    day = now.day
    dow = now.isoweekday()  # 1=Mon, 7=Sun
    
    # Month-based matching
    if "months" in item:
        if month not in item["months"]:
            return False
    
    # Day of week matching (1=Mon, 6=Sat, 7=Sun)
    if "dow" in item:
        if dow != item["dow"]:
            return False
    
    # Date range matching (start_md, end_md as [month, day])
    if "start_md" in item and "end_md" in item:
        start_m, start_d = item["start_md"]
        end_m, end_d = item["end_md"]
        
        # Convert to comparable day-of-year-like value
        current_val = month * 100 + day
        start_val = start_m * 100 + start_d
        end_val = end_m * 100 + end_d
        
        # Handle wrap-around (e.g., Nov 15 - Feb 28)
        if start_val > end_val:
            # Winter wrap: either >= start OR <= end
            if not (current_val >= start_val or current_val <= end_val):
                return False
        else:
            # Normal range
            if not (start_val <= current_val <= end_val):
                return False
    
    return True


def _evaluate_alerts(graph: Dict, weather: Dict, coast: Dict, now: datetime) -> List[Dict]:
    """Evaluate alert conditions from knowledge graph."""
    results = []
    
    for alert in graph.get("alerts", []):
        triggers = alert.get("triggers", {})
        if _evaluate_triggers(triggers, weather, coast, now):
            results.append({
                "id": alert.get("id"),
                "priority": alert.get("priority", "warning"),
                "icon": alert.get("icon", "⚠️"),
                "text": alert.get("text", ""),
            })
    
    return results


def _evaluate_micro_seasons(graph: Dict, weather: Dict, coast: Dict, now: datetime) -> List[Dict]:
    """Evaluate micro-season conditions."""
    results = []
    
    for season in graph.get("micro_seasons", []):
        # First check date constraints
        if not _check_date_range(season, now):
            continue
        
        # Then check conditional triggers (if any)
        triggers = season.get("triggers", {})
        if not _evaluate_triggers(triggers, weather, coast, now):
            continue
        
        results.append({
            "id": season.get("id"),
            "name": season.get("name"),
            "priority": season.get("priority", "flavor"),
            "vibe": season.get("vibe", ""),
        })
    
    return results


def _evaluate_sensory(graph: Dict, weather: Dict, coast: Dict, now: datetime) -> List[Dict]:
    """Evaluate sensory trigger conditions."""
    results = []
    
    for sensory in graph.get("sensory", []):
        triggers = sensory.get("triggers", {})
        if _evaluate_triggers(triggers, weather, coast, now):
            results.append({
                "id": sensory.get("id"),
                "priority": sensory.get("priority", "flavor"),
                "icon": sensory.get("icon", ""),
                "text": sensory.get("text", ""),
            })
    
    return results


def _evaluate_infrastructure(graph: Dict, weather: Dict, coast: Dict, now: datetime) -> List[Dict]:
    """Evaluate infrastructure intel conditions."""
    results = []
    
    for item in graph.get("infrastructure", []):
        triggers = item.get("triggers", {})
        if _evaluate_triggers(triggers, weather, coast, now):
            results.append({
                "id": item.get("id"),
                "priority": item.get("priority", "flavor"),
                "icon": item.get("icon", "📍"),
                "text": item.get("text", ""),
            })
    
    return results


def _evaluate_flooding(graph: Dict, weather: Dict, coast: Dict) -> Optional[Dict]:
    """Evaluate flooding conditions based on thresholds."""
    thresholds = graph.get("thresholds", {})
    zones = graph.get("flooding_zones", {})
    
    sound_ft = coast.get("observed_level_ft") or 0
    wind_deg = weather.get("wind_deg")
    
    # Determine wind direction context
    is_sw_wind = wind_deg is not None and 200 <= wind_deg <= 260
    is_ne_wind = wind_deg is not None and ((0 <= wind_deg <= 70) or wind_deg >= 330)
    
    major_ft = thresholds.get("sound_flood_major_ft", 4.5)
    moderate_ft = thresholds.get("sound_flood_moderate_ft", 3.0)
    minor_ft = thresholds.get("sound_flood_minor_ft", 2.0)
    blowout_ft = thresholds.get("sound_blowout_ft", 0.5)
    
    if sound_ft >= major_ft:
        return {
            "priority": "critical",
            "icon": "🚨",
            "text": f"MAJOR FLOODING: Sound at {sound_ft:.1f} ft. {zones.get('first_to_flood', 'Low areas')} likely impassable.",
        }
    elif sound_ft >= moderate_ft:
        wind_context = "SW winds still piling water in." if is_sw_wind else "Should drain as wind shifts."
        return {
            "priority": "warning",
            "icon": "🌊",
            "text": f"Moderate flooding: Sound at {sound_ft:.1f} ft. {zones.get('second_to_flood', 'Roads')} may have water. {wind_context}",
        }
    elif sound_ft >= minor_ft and is_sw_wind:
        return {
            "priority": "warning",
            "icon": "🌊",
            "text": f"Rising water: SW wind pushing sound to {sound_ft:.1f} ft. Watch the bulkheads.",
        }
    elif sound_ft < blowout_ft and is_ne_wind:
        return {
            "priority": "flavor",
            "icon": "📉",
            "text": "Blowout conditions: North wind emptied the harbor. Watch for grounding at the dock.",
        }
    
    return None


def get_rich_context(
    date_obj: datetime,
    weather_data: Dict[str, Any],
    coast_data: Dict[str, Any],
) -> List[str]:
    """
    Evaluate knowledge graph against current conditions.
    
    Args:
        date_obj: Current datetime for calendar/time checks
        weather_data: Weather service data (wind_mph, wind_deg, rain_last_24h_in, outdoor_temp)
        coast_data: Coast service sound_level data (observed_level_ft)
    
    Returns:
        List of formatted flag strings, prioritized (critical first), max 5
    """
    graph = _load_graph()
    if not graph:
        return []
    
    all_flags: List[Dict] = []
    
    # 1. Evaluate alerts (highest priority)
    alerts = _evaluate_alerts(graph, weather_data, coast_data, date_obj)
    all_flags.extend(alerts)
    
    # 2. Evaluate flooding (computed from thresholds)
    flood_flag = _evaluate_flooding(graph, weather_data, coast_data)
    if flood_flag:
        all_flags.append(flood_flag)
    
    # 3. Evaluate sensory triggers
    sensory = _evaluate_sensory(graph, weather_data, coast_data, date_obj)
    all_flags.extend(sensory)
    
    # 4. Evaluate infrastructure intel
    infrastructure = _evaluate_infrastructure(graph, weather_data, coast_data, date_obj)
    all_flags.extend(infrastructure)
    
    # 5. Evaluate micro-seasons (with random sampling to avoid repetition)
    seasons = _evaluate_micro_seasons(graph, weather_data, coast_data, date_obj)
    # Only include ~35% of matching seasons to add variety
    sampled_seasons = [s for s in seasons if random.random() < 0.35]
    for season in sampled_seasons:
        all_flags.append({
            "priority": season["priority"],
            "icon": "📅",
            "text": f"SEASON: {season['name']}. {season['vibe']}",
        })
    
    # Sort by priority (critical > warning > flavor)
    priority_order = {"critical": 0, "warning": 1, "flavor": 2}
    all_flags.sort(key=lambda x: priority_order.get(x.get("priority", "flavor"), 2))
    
    # Format as strings and limit to 5
    formatted = []
    for flag in all_flags[:5]:
        icon = flag.get("icon", "")
        text = flag.get("text", "")
        formatted.append(f"{icon} {text}".strip())
    
    if formatted:
        log(f"Context engine produced {len(formatted)} flags")
    
    return formatted


def get_random_riddle_topic(exclude_recent: List[str] = None) -> str:
    """
    Get a random riddle topic from knowledge graph.
    
    Args:
        exclude_recent: List of recent topics to avoid (from riddle_history.json)
    
    Returns:
        A riddle topic string
    """
    graph = _load_graph()
    topics = graph.get("riddle_topics", [])
    
    if not topics:
        return "Something from the OBX"
    
    # Filter out recent topics if provided
    if exclude_recent:
        exclude_lower = [t.lower() for t in exclude_recent]
        available = [t for t in topics if t.lower() not in exclude_lower]
        if available:
            topics = available
    
    return random.choice(topics)


if __name__ == "__main__":
    # Test the context engine
    from datetime import datetime
    
    print("Testing Context Engine...")
    print("-" * 50)
    
    # Simulate various conditions
    test_cases = [
        {
            "name": "Calm May day (midge conditions)",
            "weather": {"wind_mph": 4, "wind_deg": 180, "rain_last_24h_in": 0, "outdoor_temp": 75},
            "coast": {"observed_level_ft": 1.2},
            "date": datetime(2026, 5, 15, 14, 0),
        },
        {
            "name": "Heavy rain (septic danger)",
            "weather": {"wind_mph": 15, "wind_deg": 220, "rain_last_24h_in": 2.0, "outdoor_temp": 65},
            "coast": {"observed_level_ft": 2.5},
            "date": datetime(2026, 6, 10, 10, 0),
        },
        {
            "name": "January ghost season",
            "weather": {"wind_mph": 10, "wind_deg": 45, "rain_last_24h_in": 0, "outdoor_temp": 45},
            "coast": {"observed_level_ft": 0.8},
            "date": datetime(2026, 1, 17, 8, 0),
        },
        {
            "name": "West wind (peat smoke)",
            "weather": {"wind_mph": 15, "wind_deg": 270, "rain_last_24h_in": 0, "outdoor_temp": 70},
            "coast": {"observed_level_ft": 1.0},
            "date": datetime(2026, 4, 20, 12, 0),
        },
    ]
    
    for case in test_cases:
        print(f"\n{case['name']}:")
        flags = get_rich_context(case["date"], case["weather"], case["coast"])
        if flags:
            for flag in flags:
                print(f"  {flag}")
        else:
            print("  (no flags)")
    
    print("\n" + "-" * 50)
    print("Random riddle topic:", get_random_riddle_topic())
