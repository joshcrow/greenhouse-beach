import os
import shutil
import time
from datetime import datetime

import cv2


INCOMING_DIR = "/app/data/incoming"
ARCHIVE_ROOT = "/app/data/archive"

# L2: Image quality thresholds (brightness 0-255 scale)
BRIGHTNESS_MIN_NIGHT = 10.0  # Below this = night image, archive separately
BRIGHTNESS_MIN_DIM = 30.0  # Below this = dim but valid, log warning
BRIGHTNESS_MAX_OVEREXPOSED = 250.0  # Above this = overexposed, reject


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
    valid_exts = {".jpg", ".jpeg", ".png"}
    for name in os.listdir(INCOMING_DIR):
        if name.endswith(".tmp"):
            continue

        ext = os.path.splitext(name)[1].lower()
        if ext not in valid_exts:
            continue

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

        # Threshold check - widened to preserve dawn/dusk golden hour photos
        # L2: Using named constants instead of magic numbers
        if mean_brightness < BRIGHTNESS_MIN_NIGHT:
            now = datetime.utcnow()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            day = now.strftime("%d")
            basename = os.path.basename(path)
            dest_dir = os.path.join(ARCHIVE_ROOT, "_night", year, month, day)
            ensure_directory(dest_dir)
            dest = os.path.join(dest_dir, basename)
            shutil.move(path, dest)
            log(
                f"Archived night image '{path}' -> '{dest}' (mean luminance {mean_brightness:.2f})."
            )
            return

        if mean_brightness > BRIGHTNESS_MAX_OVEREXPOSED:
            log(
                f"Rejected: Luminance {mean_brightness:.2f} too high (overexposed) for '{path}', deleting."
            )
            os.remove(path)
            return

        # Log warning for dim images but still archive them
        if mean_brightness < BRIGHTNESS_MIN_DIM:
            log(
                f"Note: Low-light image '{path}' (luminance {mean_brightness:.2f}) - archiving anyway."
            )

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
