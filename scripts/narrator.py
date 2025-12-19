import os
from datetime import datetime
from typing import Any, Dict

import google.generativeai as genai

import weather_service


def log(message: str) -> None:
    """Simple timestamped logger (aligned with ingestion/curator)."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [narrator] {message}", flush=True)


def init_model(model_name: str | None = None) -> genai.GenerativeModel:
    """Initialize Gemini model using GEMINI_API_KEY from the environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("WARNING: GEMINI_API_KEY is not set; generation calls will fail.")
    genai.configure(api_key=api_key)

    effective_model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    return genai.GenerativeModel(effective_model)


def sanitize_data(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp sensor data to safe ranges, replacing out-of-bounds values with None.

    Requirements from REQ-3.1:
    - Temp:    -10°F to 130°F
    - Humidity: 0% to 100%
    """

    sanitized: Dict[str, Any] = dict(sensor_data)

    # Temperature
    if "temp" in sanitized:
        try:
            value = float(sanitized["temp"])
            if value < -10.0 or value > 130.0:
                log(
                    f"WARNING: Temperature value out of bounds ({value}); "
                    "replacing with None."
                )
                sanitized["temp"] = None
            else:
                sanitized["temp"] = value
        except (TypeError, ValueError):
            log("WARNING: Temperature value not numeric; replacing with None.")
            sanitized["temp"] = None

    # Humidity
    if "humidity" in sanitized:
        try:
            value = float(sanitized["humidity"])
            if value < 0.0 or value > 100.0:
                log(
                    f"WARNING: Humidity value out of bounds ({value}); "
                    "replacing with None."
                )
                sanitized["humidity"] = None
            else:
                sanitized["humidity"] = value
        except (TypeError, ValueError):
            log("WARNING: Humidity value not numeric; replacing with None.")
            sanitized["humidity"] = None

    return sanitized


def build_prompt(sanitized_data: Dict[str, Any]) -> str:
    """Construct the narrative prompt enforcing persona and safety constraints."""

    lines = [
        "You are a greenhouse newsletter narrator. Your style is scientific yet witty.",
        "",
        "RULES:",
        "- Do NOT list every sensor reading. The email already has data tables.",
        "- Only mention specific numbers if they represent significant conditions:",
        "  * Freezing temps (below 35°F)",
        "  * Extreme heat (above 90°F)", 
        "  * High winds (above 20 mph)",
        "  * Very low humidity (below 30%)",
        "  * Very high humidity (above 85%)",
        "- Use short, punchy sentences. 2-3 sentences per paragraph max.",
        "- Use <b>bold tags</b> to highlight alerts or key conditions.",
        "  Examples: '<b>Frost warning</b> for tonight.' or '<b>Strong winds</b> expected.'",
        "- Do not use emojis.",
        "- Focus on actionable insights: Should they vent? Water? Protect from cold?",
        "",
        "DATA (for context only, do not recite these numbers):",
        str(sanitized_data),
        "",
        "OUTPUT FORMAT (follow exactly):",
        "",
        "SUBJECT: <Urgency-based subject line, 5-8 words. Lead with the most important condition.",
        "         Examples: 'High Wind Alert: 34mph Gusts Today'",
        "                   'Warm and Humid Through the Weekend'",
        "                   'Perfect Growing Conditions Today'>",
        "",
        "HEADLINE: <Conversational summary, 8-12 words>",
        "",
        "BODY: <Two short paragraphs. First: current conditions and feel. Second: what to expect or do.>",
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
    try:
        model = init_model()
        response = model.generate_content(prompt)
        raw_text = _extract_text(response)
        if not raw_text:
            log("WARNING: Primary Gemini model response had no text; will try fallback model.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with gemini-2.5-flash: {exc}")

    # Fallback attempt: gemini-flash-latest if first failed
    if not raw_text:
        try:
            log("Attempting fallback generation with model 'gemini-flash-latest'.")
            model = init_model("gemini-flash-latest")
            response = model.generate_content(prompt)
            raw_text = _extract_text(response)
            if not raw_text:
                log("WARNING: Gemini (gemini-flash-latest) response had no text; returning fallback message.")
        except Exception as exc:  # noqa: BLE001
            log(f"Error during Gemini generation with gemini-flash-latest: {exc}")

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
        models = list(genai.list_models())
        for m in models:
            print(f"MODEL: {getattr(m, 'name', m)}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while listing models: {exc}")

    _, _, summary, augmented = generate_update(test_data)
    print("\n--- Generated Update ---\n")
    print(summary)
    print("\n--- Augmented Data ---\n")
    print(augmented)

