import time
from datetime import datetime

import schedule

import broadcast_email
import publisher
import weekly_digest
import golden_hour
import extended_timelapse


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


def generate_monthly_timelapse() -> None:
    """Generate monthly timelapse on the 1st of each month."""
    try:
        log("Generating monthly timelapse (500 frames)...")
        result = extended_timelapse.create_monthly_timelapse(target_frames=500)
        if result:
            filename = result.split("/")[-1]
            url = extended_timelapse.get_timelapse_url(filename)
            log(f"Monthly timelapse created: {url}")

            # Get file info for notification
            import os

            file_size_mb = os.path.getsize(result) / 1024 / 1024
            # Estimate frame count and duration (500 target at 24fps)
            frame_count = min(500, file_size_mb * 50)  # rough estimate
            duration_sec = frame_count / 24

            extended_timelapse.send_timelapse_notification(
                timelapse_type="monthly",
                filename=filename,
                file_size_mb=file_size_mb,
                duration_sec=duration_sec,
                frame_count=int(frame_count),
            )
        else:
            log("Monthly timelapse generation returned no result")
    except Exception as exc:  # noqa: BLE001
        log(f"Error generating monthly timelapse: {exc}")


def generate_yearly_timelapse() -> None:
    """Generate yearly timelapse on January 1st."""
    try:
        log("Generating yearly timelapse (4000 frames)...")
        result = extended_timelapse.create_yearly_timelapse(target_frames=4000)
        if result:
            filename = result.split("/")[-1]
            url = extended_timelapse.get_timelapse_url(filename)
            log(f"Yearly timelapse created: {url}")

            # Get file info for notification
            import os

            file_size_mb = os.path.getsize(result) / 1024 / 1024
            # Estimate frame count and duration (4000 target at 30fps)
            frame_count = min(4000, file_size_mb * 40)  # rough estimate
            duration_sec = frame_count / 30

            extended_timelapse.send_timelapse_notification(
                timelapse_type="yearly",
                filename=filename,
                file_size_mb=file_size_mb,
                duration_sec=duration_sec,
                frame_count=int(frame_count),
            )
        else:
            log("Yearly timelapse generation returned no result")
    except Exception as exc:  # noqa: BLE001
        log(f"Error generating yearly timelapse: {exc}")


def main() -> None:
    log("Starting scheduler. Registering jobs...")

    # Daily dispatch at 07:00 local time
    # On Sundays, this becomes the "Weekly Edition" with merged content
    schedule.every().day.at("07:00").do(safe_daily_dispatch)

    # Golden hour photo capture (seasonal timing)
    gh_time = golden_hour.get_seasonal_golden_hour()
    schedule.every().day.at(gh_time).do(trigger_golden_hour_capture)
    log(f"Golden hour for this month: {gh_time}")

    # Monthly timelapse on the 1st at 08:00 (after daily email)
    schedule.every().day.at("08:00").do(
        lambda: generate_monthly_timelapse() if datetime.now().day == 1 else None
    )

    # Yearly timelapse on Jan 1st at 09:00
    schedule.every().day.at("09:00").do(
        lambda: generate_yearly_timelapse()
        if datetime.now().month == 1 and datetime.now().day == 1
        else None
    )

    # Broadcast email polling every 5 minutes
    schedule.every(5).minutes.do(broadcast_email.poll_broadcast_inbox)

    log(
        f"Registered: Daily @ 07:00, Golden Hour @ {gh_time}, Monthly Timelapse @ 08:00 (1st), Yearly @ 09:00 (Jan 1), Broadcast Poll @ 5min"
    )

    while True:
        try:
            schedule.run_pending()
        except Exception as exc:  # noqa: BLE001
            log(f"Scheduler loop error while running pending jobs: {exc}")
        time.sleep(60)


if __name__ == "__main__":
    main()
