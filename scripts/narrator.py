import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google import genai
from pydantic import BaseModel, Field

import coast_sky_service
import weather_service
from utils.logger import create_logger
from utils.io import atomic_write_json, atomic_read_json


# =============================================================================
# PYDANTIC MODELS FOR GEMINI STRUCTURED OUTPUT
# =============================================================================

class NarrativeResponse(BaseModel):
    """Structured output schema for Gemini narrative generation."""
    subject: str = Field(description="5-8 word casual subject line in sentence case, no emojis")
    headline: str = Field(description="8-12 word friendly summary in sentence case")
    body: str = Field(description="1-2 short paragraphs with the narrative")


class RiddleResponse(BaseModel):
    """Structured output schema for riddle generation."""
    riddle: str = Field(description="The riddle question")
    answer: str = Field(description="The riddle answer, 1-3 words")

# Lazy settings loader for app.config integration
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings

# Load config from app.config.settings with env var fallback
_cfg = _get_settings()
_RIDDLE_STATE_PATH = _cfg.riddle_state_path if _cfg else os.getenv("RIDDLE_STATE_PATH", "/app/data/riddle_state.json")
_RIDDLE_HISTORY_PATH = os.getenv("RIDDLE_HISTORY_PATH", "/app/data/riddle_history.json")
_HISTORY_PATH = os.getenv("NARRATIVE_HISTORY_PATH", "/app/data/narrative_history.json")
_INJECTION_PATH = os.getenv("NARRATIVE_INJECTION_PATH", "/app/data/narrative_injection.json")


def to_sentence_case(text: str) -> str:
    """Convert text to sentence case (first letter caps, rest lowercase).
    
    Preserves capitalization of known proper nouns and abbreviations.
    """
    if not text:
        return text
    
    # Known proper nouns/abbreviations to preserve
    preserve = {'Colington', 'Harbour', 'OBX', 'NC', 'Outer Banks', 'Jennette'}
    
    # First, lowercase everything then capitalize first letter
    result = text[0].upper() + text[1:].lower() if len(text) > 1 else text.upper()
    
    # Restore preserved words
    for word in preserve:
        # Case-insensitive replacement
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        result = pattern.sub(word, result)
    
    return result


def strip_emojis(text: str) -> str:
    """Remove emojis from text while preserving other characters.

    Used to ensure subject/headline/body are emoji-free while
    keeping emojis in data tables for good UX.
    """
    # Regex pattern covering common emoji Unicode ranges
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"  # dingbats
        "\U000024c2-\U0001f251"  # enclosed characters
        "\U0001f900-\U0001f9ff"  # supplemental symbols
        "\U0001fa00-\U0001fa6f"  # chess symbols
        "\U0001fa70-\U0001faff"  # symbols extended-A
        "\U00002600-\U000026ff"  # misc symbols (sun, moon, etc)
        "\U0000fe0f"  # variation selector
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()


log = create_logger("narrator")


# Global client instance (lazy init)
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client using GEMINI_API_KEY from config/environment.

    Raises:
        ValueError: If GEMINI_API_KEY is not set (fail-fast).
    """
    global _client
    if _client is None:
        cfg = _get_settings()
        api_key = cfg.gemini_api_key if cfg else os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Cannot initialize Gemini client."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def get_model_name(model_name: str | None = None) -> str:
    """Get the effective model name from parameter, config, or environment."""
    if model_name:
        return model_name
    cfg = _get_settings()
    return cfg.gemini_model if cfg else os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


def sanitize_data(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp sensor data to safe ranges, replacing out-of-bounds values with None.

    Requirements from REQ-3.1:
    - Temp:    -10°F to 130°F
    - Humidity: 0% to 100%
    """

    sanitized: Dict[str, Any] = dict(sensor_data)

    # Temperature keys to sanitize (all variants used in the system)
    temp_keys = [
        "temp",
        "interior_temp",
        "exterior_temp",
        "outdoor_temp",
        "satellite_2_temperature",
        "satellite-2_satellite_2_temperature",
        "high_temp",
        "low_temp",
        "tomorrow_high",
        "tomorrow_low",
    ]

    # Humidity keys to sanitize
    humidity_keys = [
        "humidity",
        "interior_humidity",
        "exterior_humidity",
        "humidity_out",
        "satellite_2_humidity",
        "satellite-2_satellite_2_humidity",
    ]

    # Sanitize all temperature values
    for key in temp_keys:
        if key in sanitized and sanitized[key] is not None:
            try:
                value = float(sanitized[key])
                if value < -10.0 or value > 130.0:
                    log(
                        f"WARNING: {key} value out of bounds ({value}); "
                        "replacing with None."
                    )
                    sanitized[key] = None
                else:
                    sanitized[key] = value
            except (TypeError, ValueError):
                log(f"WARNING: {key} value not numeric; replacing with None.")
                sanitized[key] = None

    # Sanitize all humidity values
    for key in humidity_keys:
        if key in sanitized and sanitized[key] is not None:
            try:
                value = float(sanitized[key])
                if value < 0.0 or value > 100.0:
                    log(
                        f"WARNING: {key} value out of bounds ({value}); "
                        "replacing with None."
                    )
                    sanitized[key] = None
                else:
                    sanitized[key] = value
            except (TypeError, ValueError):
                log(f"WARNING: {key} value not numeric; replacing with None.")
                sanitized[key] = None

    return sanitized


def build_prompt(
    sanitized_data: Dict[str, Any],
    history: list[Dict[str, Any]] = None,
    is_weekly: bool = False,
    injection: Optional[Dict[str, Any]] = None,
) -> str:
    """Construct the narrative prompt enforcing persona and safety constraints.
    
    Args:
        sanitized_data: Sensor and weather data dict
        history: List of past narrative entries for continuity
        is_weekly: If True, generate Sunday "Week in Review" edition
        injection: Optional one-time message to include (e.g., birthday)
    """

    lines = [
        "ROLE: You are 'The Canal Captain', a grumpy but capable local in Colington Harbour, NC.",
        "TASK: Write a status update for a family greenhouse based on the data provided.",
        "",
        "THE PERSONA (STRICT ADHERENCE):",
        "- VOICE: Dry, salty, pragmatic. You sound like a retired fisherman checking his gauges.",
        "- LOCAL KNOWLEDGE: You live on the sound. You know the sound floods, the tourists can't drive, and the salt eats everything.",
        "- BREVITY: Short sentences. No fluff. No 'Welcome to the update.' Just the facts.",
        "- VIBE: You treat the greenhouse like a boat. It needs to be ship-shape.",
        "",
        "GEOGRAPHY & SLANG:",
        "- Use 'Colington' (referring to the neighborhood).",
        "- Use 'the sound' (Albemarle Sound).",
        "- Use 'the bypass' (the main highway, usually with disdain).",
        "- Never say 'OBX' or 'The Outer Banks'. That's for tourists. Say 'here' or 'the island'.",
        "",
        "DATA RULES:",
        "- If Temp > 90F: Complaint about humidity or 'dog days'.",
        "- If Temp < 35F: Warning about pipes freezing or frost on the windshield.",
        "- If Wind > 20mph: Mention 'whitecaps in the sound'.",
        "",
        "SOUND WATER LEVEL RULES (Wind-Driven, from 'sound_level' data):",
        "- CRITICAL CONTEXT: The Albemarle Sound acts like a bathtub.",
        "  - Wind FROM SW/W = Pushes water INTO Colington (Rising/Flooding).",
        "  - Wind FROM NE/N = Pushes water AWAY from Colington (Low/Blow-out).",
        "  - Water levels lag behind wind shifts by 3-6 hours.",
        "- INTERPRETING 'sound_level.observed_level_ft':",
        "  - < 0.5 ft (LOW): Warning. 'Water is blown out. Watch for grounding at the dock.'",
        "  - 0.5 - 2.0 ft (NORMAL): Do not mention water levels unless specifically asked.",
        "  - 2.0 - 3.0 ft (MINOR): 'Water's creeping over the bulkheads.'",
        "  - 3.0 - 4.5 ft (MODERATE): <b>Bold warning.</b> 'Colington Road or low yards may have water.'",
        "  - > 4.5 ft (MAJOR): <b>URGENT ALERT.</b> 'Severe soundside flooding likely.'",
        "- CONNECTING WIND & WATER (Causal Phrasing):",
        "  - IF (Level > 2.0) AND (Wind is SW/W): 'Strong SW winds are piling water into the harbor.'",
        "  - IF (Level > 2.0) AND (Wind is NE/N): 'Water is still high, but the North wind should help drain it soon.' (Handle the lag).",
        "  - IF (Level < 0.5) AND (Wind is NE/N): 'Strong North winds have pushed the water out.'",
        "- IGNORE 'tide_summary' and 'ocean_tides' completely. Ocean tides do not affect the harbor.",
        "",
        "FORMATTING:",
        "- <b>Bold</b> ONLY specifically dangerous alerts.",
        "- NO EMOJIS.",
        "- NO MARKDOWN HEADERS (###).",
        "- ALWAYS include degree symbol (°) when mentioning temperatures (e.g., '68°' not '68').",
        "",
    ]

    # Add history section for continuity
    if history:
        if is_weekly:
            # Sunday logbook review mode
            lines.append("THE WEEK'S LOG:")
            lines.append("")
            for entry in history:
                date = entry.get("date", "Unknown")
                headline = entry.get("headline", "")
                body = entry.get("body", "")[:300]  # Truncate for prompt size
                lines.append(f"[{date}] - {headline}")
                lines.append(f"  {body}...")
                lines.append("")
            lines.append("SUNDAY LOGBOOK REVIEW:")
            lines.append("You are reviewing the week's log. Summarize the battles we fought against the elements.")
            lines.append("1. Paragraph 1: The week's recap. Did we freeze? Did we roast? Be specific based on the archives.")
            lines.append("2. Paragraph 2: The look ahead. Prepare the crew for next week.")
            lines.append("")
            lines.append("HEADLINE: A summary of the week's weather wars.")
            lines.append("SUBJECT: Weekly Log: [Short Summary]")
            lines.append("")
        else:
            # Daily mode - reference recent history for continuity
            lines.append("NARRATIVE HISTORY (for continuity):")
            lines.append("Recent narratives from the past few days:")
            lines.append("")
            for entry in history[-3:]:  # Last 3 days for daily mode
                date = entry.get("date", "Unknown")
                headline = entry.get("headline", "")
                lines.append(f"[{date}] - {headline}")
            lines.append("")
            lines.append("CONTINUITY TIPS:")
            lines.append("- Reference previous weather if relevant ('After yesterday's wind...').")
            lines.append("- Don't repeat the same phrases or observations from recent days.")
            lines.append("- Build on the story — this is a serial, not isolated updates.")
            lines.append("")

    # Add one-time injection if present (birthdays, special events, etc.)
    if injection and injection.get("message"):
        lines.append("SPECIAL MESSAGE (MUST INCLUDE IN NARRATIVE):")
        lines.append(f"  {injection['message']}")
        if injection.get("priority") == "high":
            lines.append("  (HIGH PRIORITY: Work this into the opening of your narrative)")
        else:
            lines.append("  (Weave this naturally into the narrative)")
        lines.append("")

    lines.extend([
        "DATA:",
        str(sanitized_data),
        "",
        "OUTPUT:",
        "",
        "SUBJECT: <5-8 words, casual, SENTENCE CASE. No emojis, no HTML.",
        "         Examples: 'Windy one today' / 'Looking good out there' / 'Frost tonight, heads up'>",
        "",
        "HEADLINE: <8-12 words, friendly summary. SENTENCE CASE.>",
        "",
        "BODY: <1-2 short paragraphs. What's the vibe? Anything to watch for?>",
    ])

    return "\n".join(lines)


def _extract_text(response: Any) -> str | None:
    """Best-effort extraction of text from a Gemini response object."""
    text = getattr(response, "text", None)
    if text:
        return text
    if hasattr(response, "candidates"):
        try:
            return response.candidates[0].content.parts[0].text  # type: ignore[index]
        except Exception:  # noqa: BLE001
            return None


def _get_riddle_state_path(test_mode: bool = False) -> str:
    """Get the appropriate riddle state path based on mode."""
    if test_mode:
        base = os.path.dirname(_RIDDLE_STATE_PATH) or "."
        return os.path.join(base, "riddle_state_test.json")
    return _RIDDLE_STATE_PATH


def _load_riddle_state(test_mode: bool = False) -> Dict[str, Any]:
    path = _get_riddle_state_path(test_mode)
    try:
        data = atomic_read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed to load riddle state: {exc}")
    return {}


def _save_riddle_state(state: Dict[str, Any], test_mode: bool = False) -> None:
    path = _get_riddle_state_path(test_mode)
    try:
        atomic_write_json(path, state)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed to save riddle state: {exc}")


def _extract_yesterday_answer(state: Dict[str, Any]) -> Optional[str]:
    try:
        if state.get("pending_riddle") is not True:
            return None
        date_str = state.get("date")
        answer = state.get("answer")
        if not date_str or not answer:
            return None
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
        if date_str != yesterday:
            return None
        return str(answer).strip() or None
    except Exception:
        return None


def _load_riddle_history() -> list[Dict[str, Any]]:
    """Load riddle history for variety tracking (last 14 riddles)."""
    return atomic_read_json(_RIDDLE_HISTORY_PATH, default=[])


def _save_riddle_to_history(riddle: str, answer: str) -> None:
    """Save a riddle to history for variety tracking."""
    try:
        history = _load_riddle_history()
        history.append({
            "date": datetime.now().date().isoformat(),
            "riddle": riddle,
            "answer": answer,
        })
        # Keep only last 14 riddles
        history = history[-14:]
        atomic_write_json(_RIDDLE_HISTORY_PATH, history)
        log(f"Saved riddle to history: {len(history)} entries")
    except Exception as exc:
        log(f"WARNING: Failed to save riddle history: {exc}")


def _get_recent_riddle_topics() -> list[str]:
    """Get list of recent riddle answers to avoid repetition."""
    history = _load_riddle_history()
    return [entry.get("answer", "") for entry in history if entry.get("answer")]


def _load_narrative_injection() -> Optional[Dict[str, Any]]:
    """Load and consume a one-time narrative injection (e.g., birthday message).
    
    The injection file is deleted after reading to ensure one-time use.
    
    Expected format:
    {
        "message": "Today is Sarah's 10th birthday!",
        "priority": "high"  # optional: "high" puts it at start of narrative
    }
    """
    if not os.path.exists(_INJECTION_PATH):
        return None
    try:
        data = atomic_read_json(_INJECTION_PATH)
        # Consume the file (one-time use)
        os.remove(_INJECTION_PATH)
        log(f"Loaded and consumed narrative injection: {data.get('message', '')[:50]}...")
        return data if isinstance(data, dict) else None
    except Exception as exc:
        log(f"WARNING: Failed to load narrative injection: {exc}")
        return None


def _load_history() -> list[Dict[str, Any]]:
    """Load narrative history from persistent storage (last 7 days)."""
    try:
        data = atomic_read_json(_HISTORY_PATH)
        return data if isinstance(data, list) else []
    except Exception as exc:
        log(f"WARNING: Failed to load narrative history: {exc}")
    return []


def _save_history(new_entry: Dict[str, Any]) -> None:
    """Save a new narrative entry to history, keeping only last 7 days."""
    try:
        history = _load_history()
        # Avoid duplicates for same date
        today = new_entry.get("date")
        history = [h for h in history if h.get("date") != today]
        history.append(new_entry)
        # Keep only last 7 entries
        history = history[-7:]
        # Atomic write
        atomic_write_json(_HISTORY_PATH, history)
        log(f"Saved narrative history: {len(history)} entries")
    except Exception as exc:
        log(f"WARNING: Failed to save narrative history: {exc}")


def _generate_joke_or_riddle_paragraph(narrative_body: str, test_mode: bool = False) -> str:
    """Generate a thematically-related joke or riddle based on the narrative.
    
    Args:
        narrative_body: The main narrative text for context
        test_mode: If True, use separate state file and log answer
    """
    state = _load_riddle_state(test_mode=test_mode)
    yesterday_answer = _extract_yesterday_answer(state)

    # Get recent riddle topics to avoid repetition
    recent_topics = _get_recent_riddle_topics()

    # Always use riddle mode - answer revealed next day
    mode = "riddle"
    intro = ""
    if yesterday_answer:
        intro = f"Yesterday's riddle answer: {yesterday_answer}"

    prompt_lines = [
        "ROLE: You are that same salty Colington Harbour local.",
        "TASK: Write a 'Who am I?' riddle. The answer will be revealed tomorrow.",
        "",
        "THEME: Coastal Living, Maintenance, & Local Annoyances, aquatic life, surfing, local resturants, dog walking.",
        "RULES:",
        "1. Subject must be something tangible ",
        "2. Personify the object. Make it sound annoying, relentless, or tricky.",
        "3. Maximum 25 words.",
        "4. Dry humor only. No whimsical fairy tale stuff.",
        "",
    ]

    # Add recent topics to avoid
    if recent_topics:
        prompt_lines.append("AVOID THESE RECENT TOPICS (already used in past 2 weeks):")
        prompt_lines.append(", ".join(recent_topics))
        prompt_lines.append("")

    prompt_lines.extend([
        "EXAMPLES:",
        "Output: I show up uninvited, drink all your blood, and laugh when you try to slap me. What am I?",
        "(Target: A mosquito)",
        "Output: I cost more than your car, sit in the driveway for 50 weeks a year, and rot from the inside out. What am I?",
        "(Target: A boat)",
        "",
        f"INTRO: {intro}" if intro else "",
        "",
        "INSTRUCTION:",
        "Write ONE riddle based on the vibe above. Return ONLY the riddle text.",
    ])
    prompt = "\n".join(prompt_lines)

    client = _get_client()
    model_name = get_model_name()
    raw_text = None
    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        raw_text = _extract_text(response)
    except Exception as exc:  # noqa: BLE001
        log(f"Error during joke/riddle generation with {model_name}: {exc}")

    if not raw_text:
        fallback_model = "gemini-2.0-flash-lite"
        try:
            response = client.models.generate_content(
                model=fallback_model, contents=prompt
            )
            raw_text = _extract_text(response)
        except Exception as exc:  # noqa: BLE001
            log(f"Error during joke/riddle generation with {fallback_model}: {exc}")

    paragraph = (raw_text or "").strip()
    paragraph = strip_emojis(paragraph)
    paragraph = paragraph.replace("\n", " ").strip()
    
    # Strip any "Yesterday's riddle answer: X" prefix that AI might include
    # (this is shown separately in the answer box)
    paragraph = re.sub(r"^Yesterday'?s\s+(riddle\s+)?answer:\s*\S+\s*", "", paragraph, flags=re.IGNORECASE).strip()
    
    if not paragraph:
        return ""

    if mode == "riddle":
        answer_prompt_lines = [
            "You are helping generate a riddle.",
            "Given the riddle text below, return ONLY the answer in a short phrase (no punctuation, no quotes).",
            "Do not include the riddle again.",
            "No emojis.",
            "",
            "RIDDLE:",
            paragraph,
            "",
            "ANSWER:",
        ]
        answer_prompt = "\n".join(answer_prompt_lines)
        answer_raw = None
        try:
            answer_resp = client.models.generate_content(
                model=model_name, contents=answer_prompt
            )
            answer_raw = _extract_text(answer_resp)
        except Exception as exc:  # noqa: BLE001
            log(f"Error during riddle answer generation with {model_name}: {exc}")

        if not answer_raw:
            try:
                answer_resp = client.models.generate_content(
                    model="gemini-2.0-flash-lite", contents=answer_prompt
                )
                answer_raw = _extract_text(answer_resp)
            except Exception as exc:  # noqa: BLE001
                log(
                    f"Error during riddle answer generation with gemini-2.0-flash-lite: {exc}"
                )

        answer = strip_emojis((answer_raw or "").strip())
        answer = answer.replace("\n", " ").strip()

        # Log answer in test mode so user can verify
        if test_mode:
            log(f"[TEST MODE] Riddle: {paragraph}")
            log(f"[TEST MODE] Answer: {answer}")

        _save_riddle_state(
            {
                "pending_riddle": True,
                "date": datetime.now().date().isoformat(),
                "riddle": paragraph,
                "answer": answer,
            },
            test_mode=test_mode,
        )
        # Save to history for variety tracking (skip in test mode to avoid polluting history)
        if not test_mode and answer:
            _save_riddle_to_history(paragraph, answer)
    else:
        if yesterday_answer:
            _save_riddle_state(
                {"pending_riddle": False, "date": datetime.now().date().isoformat()},
                test_mode=test_mode,
            )

    return paragraph


def generate_update(
    sensor_data: Dict[str, Any], is_weekly: bool = False, test_mode: bool = False
) -> tuple[str, str, str, str, Dict[str, Any]]:
    """Sanitize data and request a narrative update from Gemini.

    Args:
        sensor_data: Sensor and weather data dict
        is_weekly: If True, generate Sunday "Week in Review" edition
        test_mode: If True, use separate riddle state file and log answers

    Returns:
        tuple: (subject, headline, narrative_text, augmented_sensor_data)
    """

    # Optionally augment with external weather data
    try:
        weather = weather_service.get_current_weather()
        if weather:
            sensor_data = {**sensor_data, **weather}
            log(f"Augmented sensor data with external weather: {weather}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while fetching external weather: {exc}")

    # Optionally augment with coast & sky data (tides, meteor showers, moon events)
    try:
        coast_sky = coast_sky_service.get_coast_sky_summary()
        if coast_sky:
            sensor_data = {**sensor_data, **coast_sky}
            log(f"Augmented sensor data with coast & sky: {list(coast_sky.keys())}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while fetching coast & sky data: {exc}")

    sanitized = sanitize_data(sensor_data)

    # Remove current outdoor readings (prefer daily high/low for morning context)
    # Current temp/humidity at 7am is less useful than the day's range
    if "outdoor_temp" in sanitized:
        del sanitized["outdoor_temp"]
    if "humidity_out" in sanitized:
        del sanitized["humidity_out"]
    if "wind_arrow" in sanitized:
        del sanitized["wind_arrow"]

    # Load narrative history for continuity
    history = _load_history()
    log(f"Loaded narrative history: {len(history)} entries (weekly_mode={is_weekly})")

    # Check for one-time narrative injection (birthdays, special events, etc.)
    injection = _load_narrative_injection()

    prompt = build_prompt(sanitized, history=history, is_weekly=is_weekly, injection=injection)

    log(f"Generating narrative update for data: {sanitized}")

    # Default fallback values
    subject = "Greenhouse Update"
    headline = "Greenhouse Update"
    body = "The narrator encountered an error while generating today's update."

    # Structured output config for JSON response
    # Enable thinking for Gemini 3 models (improves reasoning quality)
    structured_config = {
        "response_mime_type": "application/json",
        "response_json_schema": NarrativeResponse.model_json_schema(),
        "thinking_config": {"thinking_budget": 1024},  # Enable thinking with token budget
    }

    client = _get_client()
    model_name = get_model_name()
    raw_text = None
    structured_success = False

    # First attempt: primary Gemini model with structured output
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=structured_config,
        )
        raw_text = _extract_text(response)
        if raw_text:
            try:
                narrative = NarrativeResponse.model_validate_json(raw_text)
                subject = narrative.subject
                headline = narrative.headline
                body = narrative.body
                structured_success = True
                log(f"Structured output parsed successfully from {model_name}")
            except Exception as parse_exc:
                log(f"WARNING: Structured output parsing failed: {parse_exc}")
                # Will fall through to text fallback
        else:
            log("WARNING: Primary Gemini model response had no text; will try fallback.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with {model_name}: {exc}")

    # Fallback attempt: gemini-2.0-flash-lite with structured output
    if not structured_success:
        fallback_model = "gemini-2.0-flash-lite"
        try:
            log(f"Attempting fallback generation with model '{fallback_model}'.")
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config=structured_config,
            )
            raw_text = _extract_text(response)
            if raw_text:
                try:
                    narrative = NarrativeResponse.model_validate_json(raw_text)
                    subject = narrative.subject
                    headline = narrative.headline
                    body = narrative.body
                    structured_success = True
                    log(f"Structured output parsed successfully from {fallback_model}")
                except Exception as parse_exc:
                    log(f"WARNING: Fallback structured parsing failed: {parse_exc}")
        except Exception as exc:  # noqa: BLE001
            log(f"Error during Gemini generation with {fallback_model}: {exc}")

    # TEXT FALLBACK: If structured output failed but we have raw text, try text parsing
    if not structured_success and raw_text:
        log("WARNING: Falling back to text parsing (structured output failed)")
        # Clean markdown bolding
        clean_text = (
            raw_text.replace("**SUBJECT:**", "SUBJECT:")
            .replace("**HEADLINE:**", "HEADLINE:")
            .replace("**BODY:**", "BODY:")
        )

        try:
            if "SUBJECT:" in clean_text and "HEADLINE:" in clean_text:
                part1, remainder = clean_text.split("HEADLINE:", 1)
                subject_part = part1.replace("SUBJECT:", "").strip()

                if "BODY:" in remainder:
                    part2, body_part = remainder.split("BODY:", 1)
                    headline_part = part2.strip()
                    body = body_part.strip()
                else:
                    lines = remainder.strip().split("\n", 1)
                    headline_part = lines[0].strip()
                    body = lines[1].strip() if len(lines) > 1 else ""

                if subject_part:
                    subject = subject_part
                if headline_part:
                    headline = headline_part
            elif "BODY:" in clean_text:
                _, body_part = clean_text.split("BODY:", 1)
                body = body_part.strip() or body
            else:
                body = clean_text.strip() or body
        except Exception as e:
            log(f"Error in text fallback parsing: {e}")
            body = raw_text

    # Convert markdown bold (**text**) to HTML bold (<b>text</b>)
    body_html = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", body)

    # Create plain text version by stripping HTML tags
    body_plain = re.sub(r"<[^>]+>", "", body_html)

    # Generate riddle separately (not appended to body - will be in its own card)
    riddle_text = ""
    yesterday_answer = None
    try:
        state = _load_riddle_state(test_mode=test_mode)
        yesterday_answer = _extract_yesterday_answer(state)
        riddle_text = _generate_joke_or_riddle_paragraph(body, test_mode=test_mode)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed generating riddle: {exc}")

    # Store riddle info in sensor_data for publisher to create dedicated card
    sensor_data["_riddle_text"] = riddle_text
    sensor_data["_riddle_yesterday_answer"] = yesterday_answer

    # Strip any emojis from AI-generated text (keep emojis only in data tables)
    subject = strip_emojis(subject)
    headline = strip_emojis(headline)
    
    # Enforce sentence case on subject (AI sometimes uses ALL CAPS)
    subject = to_sentence_case(subject)
    body_html = strip_emojis(body_html)
    body_plain = strip_emojis(body_plain)

    # Store narrator model in sensor_data for debug footer
    sensor_data["_narrator_model"] = model_name

    # Save narrative to history for rolling memory (continuity across days)
    today = datetime.now().date().isoformat()
    _save_history({
        "date": today,
        "subject": subject,
        "headline": headline,
        "body": body_plain,  # Use plain text for history
    })

    return subject, headline, body_html, body_plain, sensor_data


if __name__ == "__main__":
    # Simple test run with dummy data
    test_data = {
        "temp": 72,
        "humidity": 45,
        "satellite_2_temperature": 42,
        "satellite_2_humidity": 80,
        "satellite_2_pressure": 1012,
        "satellite_2_battery": 4.1,
    }
    log(f"Running narrator test with data: {test_data}")

    # List models visible to this API key for debugging
    try:
        log("Listing available Gemini models for this API key...")
        client = _get_client()
        models = client.models.list()
        for m in models:
            print(f"MODEL: {getattr(m, 'name', m)}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while listing models: {exc}")

    _, _, summary, augmented = generate_update(test_data)
    print("\n--- Generated Update ---\n")
    print(summary)
    print("\n--- Augmented Data ---\n")
    print(augmented)
