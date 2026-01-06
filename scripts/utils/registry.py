"""Sensor registry utilities for normalization.

Loads configs/registry.json and provides functions to normalize MQTT sensor keys
to logical display keys (e.g., "satellite-2_temperature" → "exterior_temp").
"""

import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from utils.logger import create_logger

log = create_logger("registry")

REGISTRY_PATH = os.getenv("REGISTRY_PATH", "/app/configs/registry.json")


@lru_cache(maxsize=1)
def load_registry() -> Dict[str, Any]:
    """Load and cache the sensor registry.
    
    Returns empty dict if registry doesn't exist (graceful fallback).
    """
    if not os.path.exists(REGISTRY_PATH):
        log(f"WARNING: Registry not found at {REGISTRY_PATH}, using empty config")
        return {}
    
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log(f"WARNING: Failed to load registry: {exc}")
        return {}


def get_normalization_mappings() -> Dict[str, str]:
    """Get the MQTT key → logical key mappings.
    
    Returns:
        Dict mapping MQTT keys (e.g., "exterior_temp") to logical keys (e.g., "interior_temp")
    """
    registry = load_registry()
    normalization = registry.get("sensor_normalization", {})
    return normalization.get("mappings", {})


def get_conversions() -> Dict[str, Dict[str, str]]:
    """Get the unit conversion rules.
    
    Returns:
        Dict mapping MQTT keys to conversion specs, e.g.:
        {"satellite-2_temperature": {"from": "C", "to": "F"}}
    """
    registry = load_registry()
    normalization = registry.get("sensor_normalization", {})
    return normalization.get("conversions", {})


def normalize_key(mqtt_key: str) -> str:
    """Convert MQTT key to logical key using registry mappings.
    
    Args:
        mqtt_key: Raw MQTT key like "satellite-2_temperature" or "exterior_temp"
    
    Returns:
        Logical key like "exterior_temp" or "interior_temp"
        Returns original key if no mapping exists.
    """
    mappings = get_normalization_mappings()
    return mappings.get(mqtt_key, mqtt_key)


def should_convert_to_f(mqtt_key: str) -> bool:
    """Check if sensor value should be converted from Celsius to Fahrenheit.
    
    Args:
        mqtt_key: Raw MQTT key
    
    Returns:
        True if value should be converted to Fahrenheit
    """
    conversions = get_conversions()
    conv = conversions.get(mqtt_key, {})
    return conv.get("from") == "C" and conv.get("to") == "F"


def convert_value(mqtt_key: str, value: float) -> float:
    """Apply any necessary unit conversions to a sensor value.
    
    Args:
        mqtt_key: Raw MQTT key
        value: Raw sensor value
    
    Returns:
        Converted value (or original if no conversion needed)
    """
    if should_convert_to_f(mqtt_key):
        return value * 9.0 / 5.0 + 32.0
    return value


def normalize_sensor_data(
    mqtt_key: str, value: float
) -> Tuple[str, float]:
    """Normalize a single sensor reading: convert key and value.
    
    Args:
        mqtt_key: Raw MQTT key (e.g., "satellite-2_temperature")
        value: Raw sensor value
    
    Returns:
        Tuple of (logical_key, converted_value)
    """
    logical_key = normalize_key(mqtt_key)
    converted_value = convert_value(mqtt_key, value)
    return logical_key, converted_value


def get_monitored_devices() -> Dict[str, list]:
    """Get device monitoring configuration from registry.
    
    Returns:
        Dict mapping device names to their sensor key prefixes for monitoring.
        Falls back to hardcoded defaults if registry not available.
    """
    registry = load_registry()
    
    # Build from registry devices
    monitored = {}
    for device in registry.get("devices", []):
        if not device.get("active", True):
            continue
        if device.get("type") != "sensor_node":
            continue
        
        device_name = device.get("device_name", "")
        # Extract logical key prefixes from sensors
        prefixes = set()
        for sensor in device.get("sensors", []):
            logical_key = sensor.get("logical_key", "")
            if logical_key:
                # Get prefix before underscore (e.g., "interior" from "interior_temp")
                prefix = logical_key.rsplit("_", 1)[0] + "_"
                prefixes.add(prefix)
        
        if prefixes:
            monitored[device_name] = list(prefixes)
    
    # Fallback to hardcoded if registry empty
    if not monitored:
        monitored = {
            "greenhouse-pi": ["interior_", "exterior_"],
            "satellite-2": ["satellite_"],
        }
    
    return monitored


def clear_cache() -> None:
    """Clear the registry cache (useful for testing or hot-reload)."""
    load_registry.cache_clear()
