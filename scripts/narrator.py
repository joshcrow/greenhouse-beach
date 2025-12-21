import os
import re
from datetime import datetime
from typing import Any, Dict

from google import genai

import coast_sky_service
import weather_service


def strip_emojis(text: str) -> str:
    """Remove emojis from text while preserving other characters.
    
    Used to ensure subject/headline/body are emoji-free while
    keeping emojis in data tables for good UX.
    """
    # Regex pattern covering common emoji Unicode ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended-A
        "\U00002600-\U000026FF"  # misc symbols (sun, moon, etc)
        "\U0000FE0F"             # variation selector
        "]+",
        flags=re.UNICODE
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
    return model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def sanitize_data(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp sensor data to safe ranges, replacing out-of-bounds values with None.

    Requirements from REQ-3.1:
    - Temp:    -10°F to 130°F
    - Humidity: 0% to 100%
    """

    sanitized: Dict[str, Any] = dict(sensor_data)

    # Temperature keys to sanitize (all variants used in the system)
    temp_keys = [
        "temp", "interior_temp", "exterior_temp", "outdoor_temp",
        "satellite_2_temperature", "satellite-2_satellite_2_temperature",
        "high_temp", "low_temp", "tomorrow_high", "tomorrow_low",
    ]
    
    # Humidity keys to sanitize
    humidity_keys = [
        "humidity", "interior_humidity", "exterior_humidity", "humidity_out",
        "satellite_2_humidity", "satellite-2_satellite_2_humidity",
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
        "You are The Greenhouse Gazette: a witty, scientific, optimistic greenhouse newsletter narrator.",
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
        "- TIDES: Only mention if tide_summary is present. Use the provided times/heights (in feet).",
        "  If is_king_tide_window is true, briefly explain higher-than-usual tides.",
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
        "SUBJECT: <Urgency-based subject line, 5-8 words. PLAIN TEXT ONLY - no bold, no markdown, no HTML tags, no emojis.",
        "         If a sensor battery is critical, include it in subject.",
        "         Examples: 'High Wind Alert - 34mph Gusts Today'",
        "                   'Satellite Battery Critical - Charge Now'",
        "                   'Perfect Growing Conditions Today'>",
        "",
        "HEADLINE: <Conversational summary, 8-12 words. No emojis.>",
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
    return None


def generate_update(sensor_data: Dict[str, Any]) -> tuple[str, str, str, Dict[str, Any]]:
    """Sanitize data and request a narrative update from Gemini.

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
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        raw_text = _extract_text(response)
        if not raw_text:
            log("WARNING: Primary Gemini model response had no text; will try fallback model.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with {model_name}: {exc}")

    # Fallback attempt: gemini-2.0-flash-lite if first failed
    if not raw_text:
        fallback_model = "gemini-2.0-flash-lite"
        try:
            log(f"Attempting fallback generation with model '{fallback_model}'.")
            response = client.models.generate_content(
                model=fallback_model,
                contents=prompt
            )
            raw_text = _extract_text(response)
            if not raw_text:
                log(f"WARNING: Gemini ({fallback_model}) response had no text; returning fallback message.")
        except Exception as exc:  # noqa: BLE001
            log(f"Error during Gemini generation with {fallback_model}: {exc}")

    # Parse the response
    subject = "Greenhouse Update"
    headline = "Greenhouse Update"
    body = "The narrator encountered an error while generating today's update."

    if raw_text:
        # Clean markdown bolding
        clean_text = raw_text.replace("**SUBJECT:**", "SUBJECT:").replace("**HEADLINE:**", "HEADLINE:").replace("**BODY:**", "BODY:")
        
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
                    lines = remainder.strip().split('\n', 1)
                    headline_part = lines[0].strip()
                    if len(lines) > 1:
                        body = lines[1].strip()
                    else:
                        body = ""

                if subject_part: subject = subject_part
                if headline_part: headline = headline_part
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
    body = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', body)

    # Strip any emojis from AI-generated text (keep emojis only in data tables)
    subject = strip_emojis(subject)
    headline = strip_emojis(headline)
    body = strip_emojis(body)

    return subject, headline, body, sensor_data


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

