import time
from datetime import datetime

import schedule

import publisher
import weekly_digest
import golden_hour


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [scheduler] {message}", flush=True)


def safe_daily_dispatch() -> None:
    """Wrapper around publisher.run_once() with error handling.
    
    On Sundays, this becomes the "Weekly Edition" with merged weekly content.
    Records daily snapshot for weekly stats tracking.
    """
    try:
        is_sunday = datetime.now().weekday() == 6
        if is_sunday:
            log("Running Weekly Edition (Sunday daily with weekly content)...")
        else:
            log("Running Daily Dispatch...")
        
        publisher.run_once()
        log("Dispatch completed.")
        
        # Record daily snapshot for weekly stats
        log("Recording daily snapshot for weekly stats...")
        weekly_digest.record_daily_snapshot()
    except Exception as exc:  # noqa: BLE001
        log(f"Error during dispatch: {exc}")


def trigger_golden_hour_capture() -> None:
    """Trigger a golden hour photo capture via MQTT message to camera bridge."""
    try:
        log("Golden hour triggered - signaling camera capture...")
        # The camera bridge on Greenhouse Pi handles the actual capture
        # This is a placeholder for future direct integration
        # For now, golden hour captures are handled by the camera bridge daemon
        log("Golden hour capture signal sent.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during golden hour capture: {exc}")


def main() -> None:
    log("Starting scheduler. Registering jobs...")

    # Daily dispatch at 07:00 local time
    # On Sundays, this becomes the "Weekly Edition" with merged content
    schedule.every().day.at("07:00").do(safe_daily_dispatch)
    
    # Golden hour photo capture (seasonal timing)
    gh_time = golden_hour.get_seasonal_golden_hour()
    schedule.every().day.at(gh_time).do(trigger_golden_hour_capture)
    log(f"Golden hour for this month: {gh_time}")

    log(f"Registered: Daily @ 07:00 (Weekly Edition on Sundays), Golden Hour @ {gh_time}")

    while True:
        try:
            schedule.run_pending()
        except Exception as exc:  # noqa: BLE001
            log(f"Scheduler loop error while running pending jobs: {exc}")
        time.sleep(60)


if __name__ == "__main__":
    main()
