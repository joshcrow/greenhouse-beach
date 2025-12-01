import os
from datetime import datetime
from typing import Any, Dict

import google.generativeai as genai

import weather_service


def log(message: str) -> None:
    """Simple timestamped logger (aligned with ingestion/curator)."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [narrator] {message}", flush=True)


def init_model(model_name: str = "gemini-2.5-flash") -> genai.GenerativeModel:
    """Initialize Gemini model using GEMINI_API_KEY from the environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("WARNING: GEMINI_API_KEY is not set; generation calls will fail.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


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
        "You are the 'Greenhouse Gazette' narrator.",
        f"Persona: {persona}.",
        "System safety rules:",
        "- Do not invent sensors that do not exist.",
        "- Only reference the fields that are present in the provided data.",
        "",
        "Context:",
        "- Indoor readings are provided under keys like 'temp' and 'humidity'.",
        "- When present, outdoor weather is provided under keys like 'outdoor_temp',",
        "  'condition', and 'humidity_out'.",
        "- Compare inside vs. outside conditions when possible (e.g.,",
        "  'It's a gloomy rainy day outside, but the greenhouse is thriving...').",
        "",
        "Here is the latest sanitized sensor snapshot as JSON:",
        str(sanitized_data),
        "",
        "Write a short status update for the gardener, in 1 to 2 paragraphs, ",
        "explaining the current conditions and any noteworthy trends.",
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


def generate_update(sensor_data: Dict[str, Any]) -> str:
    """Sanitize data and request a narrative update from Gemini.

    First attempt uses 'gemini-2.5-flash'. If that fails, immediately retry
    with 'gemini-flash-latest'.
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
    prompt = build_prompt(sanitized)

    log(f"Generating narrative update for data: {sanitized}")

    # First attempt: gemini-2.5-flash
    try:
        model = init_model("gemini-2.5-flash")
        response = model.generate_content(prompt)
        text = _extract_text(response)
        if text:
            return text
        log("WARNING: Gemini (gemini-2.5-flash) response had no text; will try fallback model.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with gemini-2.5-flash: {exc}")

    # Fallback attempt: gemini-flash-latest
    try:
        log("Attempting fallback generation with model 'gemini-flash-latest'.")
        model = init_model("gemini-flash-latest")
        response = model.generate_content(prompt)
        text = _extract_text(response)
        if text:
            return text
        log("WARNING: Gemini (gemini-pro) response had no text; returning fallback message.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Gemini generation with gemini-pro: {exc}")

    return "The narrator encountered an error while generating today's update."


if __name__ == "__main__":
    # Simple test run with dummy data
    test_data = {"temp": 72, "humidity": 45}
    log(f"Running narrator test with data: {test_data}")

    # List models visible to this API key for debugging
    try:
        log("Listing available Gemini models for this API key...")
        models = list(genai.list_models())
        for m in models:
            print(f"MODEL: {getattr(m, 'name', m)}")
    except Exception as exc:  # noqa: BLE001
        log(f"Error while listing models: {exc}")

    summary = generate_update(test_data)
    print("\n--- Generated Update ---\n")
    print(summary)

