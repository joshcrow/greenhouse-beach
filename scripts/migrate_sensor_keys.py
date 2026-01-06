#!/usr/bin/env python3
"""One-time migration script to normalize sensor keys in historical data.

Migrates JSONL sensor log files from legacy keys to normalized logical keys:
- exterior_temp → interior_temp
- exterior_humidity → interior_humidity
- satellite-2_temperature → exterior_temp
- satellite-2_humidity → exterior_humidity
- satellite-2_battery → satellite_battery

Also handles temperature conversion (C→F) for satellite-2_temperature.

Usage:
    python scripts/migrate_sensor_keys.py [--dry-run]
    
Options:
    --dry-run    Preview changes without modifying files
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

# Key mappings (legacy → normalized)
KEY_MAPPINGS = {
    "exterior_temp": "interior_temp",
    "exterior_humidity": "interior_humidity",
    "satellite-2_temperature": "exterior_temp",
    "satellite-2_humidity": "exterior_humidity",
    "satellite-2_battery": "satellite_battery",
    "satellite-2_pressure": "exterior_pressure",
}

# Keys that need C→F conversion
CONVERT_TO_F = {"satellite-2_temperature"}


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


def migrate_entry(entry: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """Migrate a single sensor log entry to use normalized keys."""
    migrated = {}
    changes = []
    
    for key, value in entry.items():
        new_key = KEY_MAPPINGS.get(key, key)
        new_value = value
        
        # Convert temperature if needed
        if key in CONVERT_TO_F and isinstance(value, (int, float)):
            new_value = celsius_to_fahrenheit(value)
            changes.append(f"  {key}={value}°C → {new_key}={new_value:.1f}°F")
        elif new_key != key:
            changes.append(f"  {key} → {new_key}")
        
        migrated[new_key] = new_value
    
    if dry_run and changes:
        ts = entry.get("timestamp", "unknown")
        print(f"[{ts}]")
        for change in changes:
            print(change)
    
    return migrated


def migrate_jsonl_file(filepath: str, dry_run: bool = False) -> int:
    """Migrate a single JSONL file. Returns count of migrated entries."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return 0
    
    entries = []
    migrated_count = 0
    
    # Read and migrate entries
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Check if already migrated (has interior_temp key)
                if "interior_temp" in entry or "interior_humidity" in entry:
                    entries.append(entry)  # Already migrated
                    continue
                
                migrated = migrate_entry(entry, dry_run)
                entries.append(migrated)
                migrated_count += 1
            except json.JSONDecodeError as e:
                print(f"  Warning: Invalid JSON at line {line_num}: {e}")
                entries.append({"_raw": line})  # Preserve raw line
    
    # Write back if not dry run
    if not dry_run and migrated_count > 0:
        backup_path = filepath + ".backup"
        os.rename(filepath, backup_path)
        
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        
        print(f"  Migrated {migrated_count} entries (backup: {backup_path})")
    elif migrated_count > 0:
        print(f"  Would migrate {migrated_count} entries")
    
    return migrated_count


def migrate_status_json(filepath: str, dry_run: bool = False) -> bool:
    """Migrate status.json to use normalized keys."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    sensors = data.get("sensors", {})
    last_seen = data.get("last_seen", {})
    
    # Check if already migrated
    if "interior_temp" in sensors:
        print("  Already migrated")
        return False
    
    # Migrate sensors
    new_sensors = {}
    for key, value in sensors.items():
        new_key = KEY_MAPPINGS.get(key, key)
        new_value = value
        
        if key in CONVERT_TO_F and isinstance(value, (int, float)):
            new_value = celsius_to_fahrenheit(value)
            print(f"  {key}={value}°C → {new_key}={new_value:.1f}°F")
        elif new_key != key:
            print(f"  {key} → {new_key}")
        
        new_sensors[new_key] = new_value
    
    # Migrate last_seen timestamps
    new_last_seen = {}
    for key, value in last_seen.items():
        new_key = KEY_MAPPINGS.get(key, key)
        new_last_seen[new_key] = value
    
    if not dry_run:
        data["sensors"] = new_sensors
        data["last_seen"] = new_last_seen
        
        backup_path = filepath + ".backup"
        os.rename(filepath, backup_path)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        print(f"  Migrated (backup: {backup_path})")
    
    return True


def migrate_stats_json(filepath: str, dry_run: bool = False) -> bool:
    """Migrate stats_24h.json to use normalized keys."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    metrics = data.get("metrics", {})
    
    # Check if already migrated
    if "interior_temp_min" in metrics:
        print("  Already migrated")
        return False
    
    # Migrate metrics (keys like "exterior_temp_min" → "interior_temp_min")
    new_metrics = {}
    for key, value in metrics.items():
        # Split key into base and suffix (e.g., "exterior_temp_min" → "exterior_temp", "min")
        parts = key.rsplit("_", 1)
        if len(parts) == 2 and parts[1] in ("min", "max"):
            base_key = parts[0]
            suffix = parts[1]
            new_base = KEY_MAPPINGS.get(base_key, base_key)
            new_key = f"{new_base}_{suffix}"
            
            new_value = value
            if base_key in CONVERT_TO_F and isinstance(value, (int, float)):
                new_value = celsius_to_fahrenheit(value)
                print(f"  {key}={value}°C → {new_key}={new_value:.1f}°F")
            elif new_key != key:
                print(f"  {key} → {new_key}")
            
            new_metrics[new_key] = new_value
        else:
            new_metrics[key] = value
    
    if not dry_run:
        data["metrics"] = new_metrics
        
        backup_path = filepath + ".backup"
        os.rename(filepath, backup_path)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        print(f"  Migrated (backup: {backup_path})")
    
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN - No files will be modified")
        print("=" * 60)
    
    print(f"\nSensor Key Migration - {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Paths
    data_dir = os.environ.get("DATA_DIR", "/app/data")
    sensor_log_dir = os.path.join(data_dir, "sensor_log")
    status_path = os.path.join(data_dir, "status.json")
    stats_path = os.path.join(data_dir, "stats_24h.json")
    
    total_migrated = 0
    
    # Migrate status.json
    print(f"\n[1/3] Migrating {status_path}")
    migrate_status_json(status_path, dry_run)
    
    # Migrate stats_24h.json
    print(f"\n[2/3] Migrating {stats_path}")
    migrate_stats_json(stats_path, dry_run)
    
    # Migrate sensor log files
    print(f"\n[3/3] Migrating JSONL files in {sensor_log_dir}")
    if os.path.exists(sensor_log_dir):
        for filename in sorted(os.listdir(sensor_log_dir)):
            if filename.endswith(".jsonl"):
                filepath = os.path.join(sensor_log_dir, filename)
                print(f"\n  Processing {filename}...")
                count = migrate_jsonl_file(filepath, dry_run)
                total_migrated += count
    else:
        print(f"  Sensor log directory not found: {sensor_log_dir}")
    
    print("\n" + "=" * 60)
    print(f"Migration complete. Total entries migrated: {total_migrated}")
    if dry_run:
        print("(DRY RUN - no changes made)")
    print("=" * 60)


if __name__ == "__main__":
    main()
