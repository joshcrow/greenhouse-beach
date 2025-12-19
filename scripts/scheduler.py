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
    
    Also records daily snapshot for weekly digest.
    """
    try:
        log("Running Daily Dispatch job (publisher.run_once)...")
        publisher.run_once()
        log("Daily Dispatch job completed.")
        
        # Record daily snapshot for weekly digest
        log("Recording daily snapshot for weekly digest...")
        weekly_digest.record_daily_snapshot()
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Daily Dispatch job: {exc}")


def safe_weekly_digest() -> None:
    """Wrapper around weekly_digest.run_once() with error handling."""
    try:
        log("Running Weekly Digest job...")
        weekly_digest.run_once()
        log("Weekly Digest job completed.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Weekly Digest job: {exc}")


def main() -> None:
    log("Starting scheduler. Registering jobs...")

    # Daily dispatch at 07:00 local time
    schedule.every().day.at("07:00").do(safe_daily_dispatch)

    # Weekly Digest: Sunday at 08:00 (after a week of daily snapshots)
    schedule.every().sunday.at("08:00").do(safe_weekly_digest)
    
    # Golden hour photo capture (seasonal timing)
    # Note: This logs the optimal time; actual capture happens on Greenhouse Pi
    gh_time = golden_hour.get_seasonal_golden_hour()
    log(f"Golden hour for this month: {gh_time}")
    log("Camera bridge on Greenhouse Pi handles captures")

    log(f"Registered: Daily @ 07:00, Weekly @ Sunday 08:00, Golden Hour @ {gh_time}")

    while True:
        try:
            schedule.run_pending()
        except Exception as exc:  # noqa: BLE001
            log(f"Scheduler loop error while running pending jobs: {exc}")
        time.sleep(60)


if __name__ == "__main__":
    main()
