import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google import genai

import coast_sky_service
import weather_service


_RIDDLE_STATE_PATH = os.getenv("RIDDLE_STATE_PATH", "/app/data/riddle_state.json")


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


def build_prompt(sanitized_data: Dict[str, Any]) -> str:
    """Construct the narrative prompt enforcing persona and safety constraints."""

    lines = [
        "You are The Greenhouse Gazette: a witty, scientific greenhouse newsletter narrator.",
        "Location: Outer Banks, NC (coastal).",
        "",
        "RULES:",
        "- Do NOT list every sensor reading. The email already has data tables.",
        "- Only mention specific numbers if they represent significant conditions:",
        "  * Freezing temps (below 35°F)",
        "  * Extreme heat (above 90°F)",
        "  * High winds (above 20 mph)",
        "  * Very low humidity (below 30%)",
        "  * Very high humidity (above 85%)",
        "  * CRITICAL battery (below 3.4V) - mention which sensor needs charging",
        "- Do NOT mention battery levels unless they are critical (below 3.4V).",
        "- Use short, punchy sentences. 2-3 sentences per paragraph max.",
        "- Use <b>bold tags</b> to highlight alerts or key conditions.",
        "  Examples: '<b>Frost warning</b> for tonight.' or '<b>Satellite sensor needs charging</b>.'",
        "- Do not use emojis.",
        "- Focus on actionable insights: Should they vent? Water? Protect from cold? Charge a sensor?",
        "",
        "COAST & SKY (IMPORTANT - NO HALLUCINATION):",
        "- You may include 1-2 sentences about Coast & Sky ONLY if the DATA contains relevant fields.",
        "- TIDES: Only mention if tide_summary is present AND the tide is NOTABLE:",
        "  * King tide window (is_king_tide_window is true) - explain higher-than-usual tides.",
        "  * Very low tide (negative feet, good for beach walking).",
        "  * Unusually high tide (above 3.5 ft).",
        "  If tides are normal/unremarkable, do NOT mention them - the data table already shows them.",
        "- METEOR SHOWERS: Only mention if sky_summary is present with meteor_shower_name.",
        "  If is_peak_window is true, note it. Consider clouds_pct and precip_prob for visibility.",
        "  If clouds_pct > 70 or precip_prob > 50, note viewing may be limited.",
        "- MOON EVENTS: Only mention if moon_event_summary is present with full_moon_name.",
        "  Supermoons or blue moons are worth a brief mention.",
        "- If none of these keys are present, do NOT mention tides, meteors, or named moon events.",
        "",
        "DATA (for context only, do not recite raw numbers):",
        str(sanitized_data),
        "",
        "OUTPUT FORMAT (follow exactly):",
        "",
        "SUBJECT: <Urgency-based subject line, 5-8 words in SENTENCE CASE (not Title Case).",
        "         PLAIN TEXT ONLY - no bold, no markdown, no HTML tags, no emojis.",
        "         If a sensor battery is critical, include it in subject.",
        "         Examples: 'High wind alert - 34mph gusts today'",
        "                   'Satellite battery critical - charge now'",
        "                   'Perfect growing conditions today'>",
        "",
        "HEADLINE: <Conversational summary in SENTENCE CASE, 8-12 words. No emojis.>",
        "",
        "BODY: <Two short paragraphs. First: current conditions and feel. Second: what to expect or do.",
        "       If Coast & Sky data is present and notable, add a brief third sentence or short paragraph.>",
    ]

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


def _load_riddle_state() -> Dict[str, Any]:
    try:
        if os.path.exists(_RIDDLE_STATE_PATH):
            with open(_RIDDLE_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed to load riddle state: {exc}")
    return {}


def _save_riddle_state(state: Dict[str, Any]) -> None:
    try:
        tmp_path = f"{_RIDDLE_STATE_PATH}.tmp"
        os.makedirs(os.path.dirname(_RIDDLE_STATE_PATH) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, _RIDDLE_STATE_PATH)
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


def _generate_joke_or_riddle_paragraph(narrative_body: str) -> str:
    """Generate a thematically-related joke or riddle based on the narrative."""
    state = _load_riddle_state()
    yesterday_answer = _extract_yesterday_answer(state)

    # Always use riddle mode - answer revealed next day
    mode = "riddle"
    intro = ""
    if yesterday_answer:
        intro = f"Yesterday's riddle answer: {yesterday_answer}"

    prompt_lines = [
        "You are the 'Comic Relief' section of the greenhouse newsletter.",
        "Write ONE riddle as a light sign-off for today's newsletter.",
        "",
        "CRITICAL REQUIREMENTS:",
        "- You MUST write a RIDDLE, not a joke.",
        "- A riddle asks a question. The answer is NOT revealed until tomorrow's newsletter.",
        "- NEVER include the answer, punchline, or solution in your output.",
        "- NEVER use 'Because...' or any answer/explanation.",
        "",
        "RIDDLE FORMAT (follow exactly):",
        "- Start with the INTRO text if provided.",
        "- Then write a riddle question that ends with a question mark.",
        "- The riddle should be 1-2 sentences max.",
        "- Example: 'Here's today's riddle: What gets wetter the more it dries?'",
        "- Example: 'Riddle me this: I have hands but cannot clap. What am I?'",
        "",
        "THEME:",
        "- Read the NARRATIVE below for today's theme.",
        "- Make the riddle SUBTLY related (gardening, weather, plants, greenhouse life).",
        "- Do NOT reference specific numbers or sensor data.",
        "",
        "FORBIDDEN:",
        "- No answers or punchlines (e.g., 'Because...').",
        "- No emojis, markdown, or HTML.",
        "- No jokes with setup+punchline format.",
        "",
        f"INTRO: {intro}" if intro else "INTRO: (none - start directly with riddle)",
        "",
        "NARRATIVE:",
        narrative_body[:1500] if narrative_body else "A typical day at the greenhouse.",
        "",
        "OUTPUT: Return only the riddle paragraph (with INTRO if provided). No answer.",
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

        _save_riddle_state(
            {
                "pending_riddle": True,
                "date": datetime.now().date().isoformat(),
                "riddle": paragraph,
                "answer": answer,
            }
        )
    else:
        if yesterday_answer:
            _save_riddle_state(
                {"pending_riddle": False, "date": datetime.now().date().isoformat()}
            )

    return paragraph


def generate_update(
    sensor_data: Dict[str, Any], is_weekly: bool = False
) -> tuple[str, str, str, str, Dict[str, Any]]:
    """Sanitize data and request a narrative update from Gemini.

    Args:
        sensor_data: Sensor and weather data dict
        is_weekly: If True, generate Sunday "Week in Review" edition

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

    prompt = build_prompt(sanitized)

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

    joke_or_riddle = ""
    try:
        joke_or_riddle = _generate_joke_or_riddle_paragraph(body)
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: Failed generating joke/riddle paragraph: {exc}")

    if joke_or_riddle:
        if body_html and not body_html.endswith("\n"):
            body_html = body_html.rstrip()
            body_plain = body_plain.rstrip()
        body_html = f"{body_html}\n\n{joke_or_riddle}" if body_html else joke_or_riddle
        body_plain = (
            f"{body_plain}\n\n{joke_or_riddle}" if body_plain else joke_or_riddle
        )

    # Strip any emojis from AI-generated text (keep emojis only in data tables)
    subject = strip_emojis(subject)
    headline = strip_emojis(headline)
    body_html = strip_emojis(body_html)
    body_plain = strip_emojis(body_plain)

    # Store narrator model in sensor_data for debug footer
    sensor_data["_narrator_model"] = model_name

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
