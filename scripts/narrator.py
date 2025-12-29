import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google import genai

import coast_sky_service
import weather_service


_RIDDLE_STATE_PATH = os.getenv("RIDDLE_STATE_PATH", "/app/data/riddle_state.json")
_HISTORY_PATH = os.getenv("NARRATIVE_HISTORY_PATH", "/app/data/narrative_history.json")


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


def log(message: str) -> None:
    """Simple timestamped logger (aligned with ingestion/curator)."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [narrator] {message}", flush=True)


# Global client instance (lazy init)
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client using GEMINI_API_KEY from the environment.

    Raises:
        ValueError: If GEMINI_API_KEY is not set (fail-fast).
    """
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Cannot initialize Gemini client."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def get_model_name(model_name: str | None = None) -> str:
    """Get the effective model name from parameter or environment."""
    return model_name or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


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
) -> str:
    """Construct the narrative prompt enforcing persona and safety constraints.
    
    Args:
        sanitized_data: Sensor and weather data dict
        history: List of past narrative entries for continuity
        is_weekly: If True, generate Sunday "Week in Review" edition
    """

    lines = [
        "You write for The Greenhouse Gazette — quick, practical updates for a family greenhouse",
        "in Colington Harbour (Outer Banks, NC). Keep it casual and useful, like texting a neighbor.",
        "",
        "VOICE:",
        "- Brief and down-to-earth. This is a busy household.",
        "- Skip the poetry. Get to the point, but keep it friendly.",
        "- Local flavor: say 'in Colington' or 'the harbour' — not 'the Outer Banks' or 'OBX'.",
        "- Never introduce yourself. Just talk.",
        "",
        "CONTENT:",
        "- Do NOT recite sensor data. Tables handle that.",
        "- Only mention numbers for real issues: frost (<35°F), extreme heat (>90°F),",
        "  high wind (>25 mph), critical battery (<3.4V).",
        "- Keep paragraphs to 2-3 sentences MAX.",
        "- Use <b>bold</b> only for actual alerts.",
        "- No emojis.",
        "",
        "COAST & SKY:",
        "- Only if data is present AND notable: king tides, negative tides, meteor showers.",
        "- Normal conditions? Skip it — the table shows tides already.",
        "",
    ]

    # Add history section for continuity
    if history:
        if is_weekly:
            # Sunday historian mode - review the week
            lines.append("THE WEEK'S ARCHIVES:")
            lines.append("This is the Sunday Weekly Edition. Review the past week's narratives:")
            lines.append("")
            for entry in history:
                date = entry.get("date", "Unknown")
                headline = entry.get("headline", "")
                body = entry.get("body", "")[:300]  # Truncate for prompt size
                lines.append(f"[{date}] - {headline}")
                lines.append(f"  {body}...")
                lines.append("")
            lines.append("SUNDAY WEEKLY EDITION INSTRUCTIONS:")
            lines.append("You're writing the Sunday 'Week in Review'. Structure:")
            lines.append("1. Paragraph 1: Summarize the week's storylines from the Archives above.")
            lines.append("   Use specific days and events. Make it narrative, not a list.")
            lines.append("2. Paragraph 2: Today's current conditions.")
            lines.append("3. Paragraph 3: Looking ahead to next week (if forecast data available).")
            lines.append("")
            lines.append("HEADLINE: Reflect the entire week (e.g., 'A week of wind and sun').")
            lines.append("SUBJECT: Indicate it's weekly (e.g., 'Weekly recap: stormy start, sunny finish').")
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
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed to load riddle state: {exc}")
    return {}


def _save_riddle_state(state: Dict[str, Any], test_mode: bool = False) -> None:
    path = _get_riddle_state_path(test_mode)
    try:
        tmp_path = f"{path}.tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
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


def _load_history() -> list[Dict[str, Any]]:
    """Load narrative history from persistent storage (last 7 days)."""
    try:
        if os.path.exists(_HISTORY_PATH):
            with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        os.makedirs(os.path.dirname(_HISTORY_PATH) or ".", exist_ok=True)
        tmp_path = f"{_HISTORY_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, _HISTORY_PATH)
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

    # Always use riddle mode - answer revealed next day
    mode = "riddle"
    intro = ""
    if yesterday_answer:
        intro = f"Yesterday's riddle answer: {yesterday_answer}"

    prompt_lines = [
        "ROLE: You are a grumpy but lovable gardener writing for a local coastal newsletter.",
        "TASK: Write a 'Who am I?' or 'What am I?' riddle. The answer will be revealed tomorrow.",
        "",
        "THE RULES OF THE GAME:",
        "1. Pick a specific, tangible object related to the provided context (e.g., a hose, a tourist, a mosquito, humidity).",
        "2. Do NOT name the object in the riddle.",
        "3. Personify the object. Describe its annoying or funny behavior as if it were a person or a deliberate act.",
        "4. Keep it under 25 words.",
        "",
        "TONE GUIDE (HUMAN, NOT ROBOT):",
        "- Use dry, observational humor.",
        "- Avoid cheesy intro phrases like 'I am the thing that...'",
        "- Focus on the frustration or the absurdity of the object.",
        "",
        "EXAMPLES (Study these patterns):",
        "Context: Gardening",
        "Output: I spend all day lying in the grass, but the moment you try to use me, I tie myself in knots and refuse to work. What am I?",
        "(Target Answer: A garden hose)",
        "",
        "Context: Beach Life",
        "Output: I arrive every Friday with a car full of groceries, drive 15mph under the speed limit, and have no idea how a roundabout works. Who am I?",
        "(Target Answer: A weekend tourist)",
        "",
        "Context: Weather",
        "Output: You beg for me all July, but when I finally show up, you run inside and complain about the mud. What am I?",
        "(Target Answer: Rain)",
        "",
        f"INTRO: {intro}" if intro else "",
        "",
        "CURRENT CONTEXT / VIBE:",
        narrative_body[:1000] if narrative_body else "General coastal gardening chaos.",
        "",
        "INSTRUCTION:",
        "Write ONE riddle based on the context above. Do not output the answer. Do not output the logic. Return ONLY the riddle text.",
    ]
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
    if "wind_mph" in sanitized:
        del sanitized["wind_mph"]
    if "wind_deg" in sanitized:
        del sanitized["wind_deg"]
    if "wind_direction" in sanitized:
        del sanitized["wind_direction"]
    if "wind_arrow" in sanitized:
        del sanitized["wind_arrow"]

    # Load narrative history for continuity
    history = _load_history()
    log(f"Loaded narrative history: {len(history)} entries (weekly_mode={is_weekly})")

    prompt = build_prompt(sanitized, history=history, is_weekly=is_weekly)

    log(f"Generating narrative update for data: {sanitized}")

    raw_text = None

    # First attempt: primary Gemini model from configuration
    client = _get_client()
    model_name = get_model_name()
    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        raw_text = _extract_text(response)
        if not raw_text:
            log(
                "WARNING: Primary Gemini model response had no text; will try fallback model."
            )
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with {model_name}: {exc}")

    # Fallback attempt: gemini-2.0-flash-lite if first failed
    if not raw_text:
        fallback_model = "gemini-2.0-flash-lite"
        try:
            log(f"Attempting fallback generation with model '{fallback_model}'.")
            response = client.models.generate_content(
                model=fallback_model, contents=prompt
            )
            raw_text = _extract_text(response)
            if not raw_text:
                log(
                    f"WARNING: Gemini ({fallback_model}) response had no text; returning fallback message."
                )
        except Exception as exc:  # noqa: BLE001
            log(f"Error during Gemini generation with {fallback_model}: {exc}")

    # Parse the response
    subject = "Greenhouse Update"
    headline = "Greenhouse Update"
    body = "The narrator encountered an error while generating today's update."

    if raw_text:
        # Clean markdown bolding
        clean_text = (
            raw_text.replace("**SUBJECT:**", "SUBJECT:")
            .replace("**HEADLINE:**", "HEADLINE:")
            .replace("**BODY:**", "BODY:")
        )

        # We need to parse SUBJECT, HEADLINE, and BODY
        # A robust way is to split by keys
        try:
            # Split into lines to find keys, or simple string partitioning
            # Given the prompt order: SUBJECT -> HEADLINE -> BODY
            if "SUBJECT:" in clean_text and "HEADLINE:" in clean_text:
                # Split between SUBJECT and HEADLINE
                part1, remainder = clean_text.split("HEADLINE:", 1)
                subject_part = part1.replace("SUBJECT:", "").strip()

                # Split between HEADLINE and BODY (if BODY exists)
                if "BODY:" in remainder:
                    part2, body_part = remainder.split("BODY:", 1)
                    headline_part = part2.strip()
                    body = body_part.strip()
                else:
                    # No BODY marker, assume everything after HEADLINE is the body
                    # But first line might be the headline text itself
                    lines = remainder.strip().split("\n", 1)
                    headline_part = lines[0].strip()
                    if len(lines) > 1:
                        body = lines[1].strip()
                    else:
                        body = ""

                if subject_part:
                    subject = subject_part
                if headline_part:
                    headline = headline_part
            else:
                # Fallback parsing logic
                log("WARNING: Output format mismatch. Attempting partial parse.")
                # If we at least have a BODY marker, use that section
                if "BODY:" in clean_text:
                    _, body_part = clean_text.split("BODY:", 1)
                    body = body_part.strip() or body
                else:
                    # No structured markers; treat entire text as body
                    body = clean_text.strip() or body
        except Exception as e:
            log(f"Error parsing narrative response: {e}")
            # On any parsing error, fall back to the raw model text
            body = raw_text  # type: ignore[assignment]

    # Convert markdown bold (**text**) to HTML bold (<b>text</b>)
    import re

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
