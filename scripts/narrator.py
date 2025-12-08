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

    persona = "Scientific, Pithy, Concise"

    lines = [
        "You are the narrator.",
        f"Persona: {persona}.",
        "System safety rules:",
        "- Do not invent sensors that do not exist.",
        "- Only reference the fields that are present in the provided data.",
        "- Do not use emojis in the narrative text.",
        "",
        "Context:",
        "- Indoor readings are provided under keys like 'temp' and 'humidity'.",
        "- Today's weather forecast includes 'high_temp', 'low_temp', 'condition', and 'daily_wind_mph'.",
        "  Focus on these daily ranges rather than point-in-time readings.",
        "  This helps the gardener plan for the day (heat management, ventilation, etc.).",
        "- Tomorrow's forecast is available (tomorrow_high, tomorrow_low, tomorrow_condition).",
        "  Use it to provide helpful lookahead context when relevant.",
        "- Compare indoor conditions with today's outdoor forecast when useful.",
        "",
        "Here is the latest sanitized sensor snapshot as JSON:",
        str(sanitized_data),
        "",
        "Write a short status update for the gardener, in two short paragraphs telling the highlights, ",
        "explaining the current conditions and any noteworthy trends.",
        "Focus on the 'feel' of the environment rather than listing every number. Be conversational.",
        "Use simple, clear language. Avoid complex vocabulary. Weather terms are fine, but keep it casual.",
        "When mentioning temperatures, use the abbreviated format: 75ºF (not '75 degrees Fahrenheit').",
        "",
        "Output MUST follow this exact format:",
        "SUBJECT: <Engaging conversational subject line, 8-10 words. DO NOT use colons or 'Topic: Phrase' patterns.>",
        "HEADLINE: <Conversational, summary headline, up to 16 words>",
        "BODY: <The narrative text, with a blank line between the two paragraphs>",
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
            if "SUBJECT:" in clean_text and "HEADLINE:" in clean_text and "BODY:" in clean_text:
                # Split between SUBJECT and HEADLINE
                part1, remainder = clean_text.split("HEADLINE:", 1)
                subject_part = part1.replace("SUBJECT:", "").strip()
                
                # Split between HEADLINE and BODY
                part2, body_part = remainder.split("BODY:", 1)
                headline_part = part2.strip()
                
                if subject_part: subject = subject_part
                if headline_part: headline = headline_part
                if body_part.strip(): body = body_part.strip()
            else:
                # Fallback parsing logic
                log("WARNING: Output format mismatch. Attempting partial parse.")
                # If only BODY is missing, etc.
                # For safety, if parsing fails, treat whole text as body if it doesn't look like keys
                if "BODY:" in clean_text:
                     _, body = clean_text.split("BODY:", 1)
                     body = body.strip()
        except Exception as e:
            log(f"Error parsing narrative response: {e}")
            body = raw_text  # Fallback to raw text

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

