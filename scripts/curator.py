import os
import shutil
import time
from datetime import datetime

import cv2


INCOMING_DIR = "/app/data/incoming"
ARCHIVE_ROOT = "/app/data/archive"


def log(message: str) -> None:
    """Simple timestamped logger (same format as ingestion)."""
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [curator] {message}", flush=True)


def ensure_directory(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        log(f"Created directory: {path}")


def list_candidate_files() -> list[str]:
    if not os.path.isdir(INCOMING_DIR):
        return []

    entries: list[str] = []
    for name in os.listdir(INCOMING_DIR):
        full_path = os.path.join(INCOMING_DIR, name)
        if os.path.isfile(full_path):
            entries.append(full_path)
    return sorted(entries)


def archive_path_for(filename: str) -> str:
    """Compute the archive path /app/data/archive/YYYY/MM/DD/original_name."""
    now = datetime.utcnow()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    basename = os.path.basename(filename)
    dest_dir = os.path.join(ARCHIVE_ROOT, year, month, day)
    ensure_directory(dest_dir)
    return os.path.join(dest_dir, basename)


def process_file(path: str) -> None:
    """Score image by luminance and move/delete according to thresholds."""
    try:
        # Load image
        img = cv2.imread(path)
        if img is None:
            log(f"Warning: Corrupt or unreadable image '{path}', deleting.")
            os.remove(path)
            return

        # Convert to grayscale and compute mean brightness
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(gray.mean())

        # Threshold check
        if mean_brightness < 25.0:
            log(f"Rejected: Luminance {mean_brightness:.2f} too low for '{path}', deleting.")
            os.remove(path)
            return

        if mean_brightness > 242.0:
            log(f"Rejected: Luminance {mean_brightness:.2f} too high for '{path}', deleting.")
            os.remove(path)
            return

        # Passed luminance gates -> archive
        dest = archive_path_for(path)
        shutil.move(path, dest)
        log(f"Archived '{path}' -> '{dest}' (mean luminance {mean_brightness:.2f}).")

    except Exception as exc:  # noqa: BLE001
        log(f"Error processing '{path}': {exc}")
        # As a safety measure, avoid leaving obviously bad files to loop forever
        try:
            if os.path.exists(path):
                os.remove(path)
                log(f"Deleted '{path}' after error during processing.")
        except Exception as delete_exc:  # noqa: BLE001
            log(f"Failed to delete '{path}' after error: {delete_exc}")


def main() -> None:
    log("Starting curator loop. Monitoring /app/data/incoming for new images.")
    ensure_directory(INCOMING_DIR)
    ensure_directory(ARCHIVE_ROOT)

    while True:
        try:
            files = list_candidate_files()
            if files:
                log(f"Found {len(files)} file(s) to process in incoming queue.")
            for path in files:
                process_file(path)
        except KeyboardInterrupt:
            log("KeyboardInterrupt received; exiting curator loop.")
            break
        except Exception as exc:  # noqa: BLE001
            log(f"Curator loop error: {exc}")

        time.sleep(10)


if __name__ == "__main__":
    main()

