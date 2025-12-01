import time
from datetime import datetime

import schedule

import publisher


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [scheduler] {message}", flush=True)


def safe_daily_dispatch() -> None:
    """Wrapper around publisher.run_once() with error handling."""
    try:
        log("Running Daily Dispatch job (publisher.run_once)...")
        publisher.run_once()
        log("Daily Dispatch job completed.")
    except Exception as exc:  # noqa: BLE001
        log(f"Error during Daily Dispatch job: {exc}")


def main() -> None:
    log("Starting scheduler. Registering jobs...")

    # Daily dispatch at 07:00 local time
    schedule.every().day.at("07:00").do(safe_daily_dispatch)

    # Weekly Wrap placeholder: Sunday at 08:00
    # schedule.every().sunday.at("08:00").do(run_weekly_wrap)

    while True:
        try:
            schedule.run_pending()
        except Exception as exc:  # noqa: BLE001
            log(f"Scheduler loop error while running pending jobs: {exc}")
        time.sleep(60)


if __name__ == "__main__":
    main()
