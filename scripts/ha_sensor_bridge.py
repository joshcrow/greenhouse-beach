#!/usr/bin/env python3
"""Home Assistant Sensor Bridge for Greenhouse Gazette.

Reads sensor states from Home Assistant and publishes to MQTT
for the Storyteller to ingest.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict, List, Optional


def log(message: str) -> None:
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f'[{ts}] [sensor_bridge] {message}', flush=True)


# Sensor mapping: HA entity_id -> (mqtt_device, mqtt_key)
# Format: greenhouse/{device}/sensor/{key}/state
SENSOR_MAP = {
    # Interior sensors (persistent = smoothed values)
    'sensor.greenhouse_temp_persistent': ('interior', 'temp'),
    'sensor.greenhouse_humidity_persistent': ('interior', 'humidity'),
    'sensor.greenhouse_pressure_persistent': ('interior', 'pressure'),
    
    # Exterior sensors
    'sensor.greenhouse_ext_temp_persistent': ('exterior', 'temp'),
    'sensor.greenhouse_ext_humidity_persistent': ('exterior', 'humidity'),
    'sensor.greenhouse_ext_pressure_persistent': ('exterior', 'pressure'),
    
    # Raw sensor nodes (if you want both smoothed and raw)
    # 'sensor.sensor1_greenhouse_temperature': ('sensor1', 'temp'),
    # 'sensor.sensor1_greenhouse_humidity': ('sensor1', 'humidity'),
    # 'sensor.sensor2_greenhouse_temperature': ('sensor2', 'temp'),
    # 'sensor.sensor2_greenhouse_humidity': ('sensor2', 'humidity'),
}


def fetch_ha_states(ha_url: str, ha_token: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch all entity states from Home Assistant."""
    url = f'{ha_url}/api/states'
    headers = {'Authorization': f'Bearer {ha_token}'}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log(f'HA fetch error: {e}')
        return None


def publish_to_mqtt(broker_host: str, broker_port: int, topic: str, value: str,
                    username: str = None, password: str = None) -> bool:
    """Publish a single value to MQTT.
    
    Uses try/finally to ensure client cleanup on any exception (H5: prevent resource leak).
    """
    import paho.mqtt.client as mqtt
    client = None
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username and password:
            client.username_pw_set(username, password)
        client.connect(broker_host, broker_port, keepalive=30)
        client.loop_start()
        result = client.publish(topic, value, qos=1, retain=True)
        result.wait_for_publish(timeout=5)
        return result.is_published()
    except Exception as e:
        log(f'MQTT error for {topic}: {e}')
        return False
    finally:
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass  # Ignore cleanup errors


def bridge_sensors(config: Dict[str, Any]) -> int:
    """Fetch HA sensors and publish to MQTT. Returns count of published values."""
    states = fetch_ha_states(config['ha_url'], config['ha_token'])
    if not states:
        return 0
    
    # Build lookup by entity_id
    state_map = {s['entity_id']: s for s in states}
    
    published = 0
    for entity_id, (device, key) in SENSOR_MAP.items():
        if entity_id not in state_map:
            continue
        
        state = state_map[entity_id].get('state')
        if state in (None, 'unknown', 'unavailable'):
            continue
        
        # Build MQTT topic matching status_daemon expectation
        topic = f"greenhouse/{device}/sensor/{key}/state"
        
        if publish_to_mqtt(config['mqtt_host'], config['mqtt_port'], topic, state,
                           config.get('mqtt_username'), config.get('mqtt_password')):
            log(f'Published {entity_id} -> {topic}: {state}')
            published += 1
    
    return published


def load_config() -> Dict[str, Any]:
    return {
        'ha_url': os.getenv('HA_URL', 'http://localhost:8123'),
        'ha_token': os.getenv('HA_TOKEN'),
        'mqtt_host': os.getenv('MQTT_HOST', '100.94.172.114'),
        'mqtt_port': int(os.getenv('MQTT_PORT', '1883')),
        'mqtt_username': os.getenv('MQTT_USERNAME'),
        'mqtt_password': os.getenv('MQTT_PASSWORD'),
        'interval_minutes': int(os.getenv('SENSOR_INTERVAL_MINUTES', '5')),
    }


def run_once(config: Dict[str, Any]) -> bool:
    count = bridge_sensors(config)
    log(f'Bridge cycle complete: {count} sensors published')
    return count > 0


def run_daemon(config: Dict[str, Any]) -> None:
    interval = config['interval_minutes']
    log(f'Starting sensor bridge daemon, interval={interval}min')
    
    while True:
        try:
            run_once(config)
        except Exception as e:
            log(f'Error in bridge cycle: {e}')
        time.sleep(interval * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--daemon', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--interval', type=int, default=5)
    args = parser.parse_args()
    
    config = load_config()
    
    if not config.get('ha_token'):
        log('ERROR: HA_TOKEN not set')
        sys.exit(1)
    
    if args.test:
        log('Test mode - fetching sensors...')
        states = fetch_ha_states(config['ha_url'], config['ha_token'])
        if states:
            for entity_id in SENSOR_MAP.keys():
                for s in states:
                    if s['entity_id'] == entity_id:
                        print(f"  {entity_id}: {s.get('state')} {s.get('attributes', {}).get('unit_of_measurement', '')}")
        sys.exit(0)
    
    if args.daemon:
        config['interval_minutes'] = args.interval
        run_daemon(config)
    else:
        sys.exit(0 if run_once(config) else 1)


if __name__ == '__main__':
    main()
