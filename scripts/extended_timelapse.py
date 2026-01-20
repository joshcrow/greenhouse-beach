#!/usr/bin/env python3
"""Extended Timelapse Generator for Greenhouse Gazette.

Creates monthly and yearly MP4 timelapses from archived images.
Outputs to data/www/timelapses/ for web access via Tailscale.
"""

import glob
import os
import shutil
import smtplib
import ssl
import subprocess
import tempfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional

from PIL import Image

from utils.logger import create_logger
from utils.image_utils import sample_frames_evenly

log = create_logger("extended_timelapse")

# Lazy settings loader for app.config integration
_settings = None

def _get_settings():
    """Get settings lazily to avoid import-time failures."""
    global _settings
    if _settings is None:
        try:
            from app.config import settings
            _settings = settings
        except Exception:
            _settings = None
    return _settings

_cfg = _get_settings()
ARCHIVE_ROOT = _cfg.archive_path if _cfg else os.getenv("ARCHIVE_ROOT", "/app/data/archive")
OUTPUT_ROOT = os.getenv("TIMELAPSE_OUTPUT", "/app/data/www/timelapses")


def get_images_for_month(year: int, month: int) -> List[str]:
    """Get all images from a specific month, sorted chronologically."""
    images = []
    month_path = os.path.join(ARCHIVE_ROOT, str(year), f"{month:02d}")

    if not os.path.exists(month_path):
        log(f"No archive directory for {year}/{month:02d}")
        return []

    # Get all day directories
    for day_dir in sorted(os.listdir(month_path)):
        day_path = os.path.join(month_path, day_dir)
        if os.path.isdir(day_path):
            day_images = glob.glob(os.path.join(day_path, "*.jpg"))
            day_images.sort()
            images.extend(day_images)

    log(f"Found {len(images)} images for {year}/{month:02d}")
    return images


def get_images_for_year(year: int) -> List[str]:
    """Get all images from a specific year, sorted chronologically."""
    images = []
    year_path = os.path.join(ARCHIVE_ROOT, str(year))

    if not os.path.exists(year_path):
        log(f"No archive directory for {year}")
        return []

    # Get all month directories
    for month_dir in sorted(os.listdir(year_path)):
        month_path = os.path.join(year_path, month_dir)
        if os.path.isdir(month_path):
            for day_dir in sorted(os.listdir(month_path)):
                day_path = os.path.join(month_path, day_dir)
                if os.path.isdir(day_path):
                    day_images = glob.glob(os.path.join(day_path, "*.jpg"))
                    day_images.sort()
                    images.extend(day_images)

    log(f"Found {len(images)} images for {year}")
    return images


# sample_frames_evenly imported from utils.image_utils


def prepare_frames(images: List[str], temp_dir: str, max_width: int = 1280) -> int:
    """Resize and copy frames to temp directory with sequential naming for ffmpeg."""
    frame_count = 0

    for i, img_path in enumerate(images):
        try:
            img = Image.open(img_path)

            # Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Resize to max_width maintaining aspect ratio
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                # Ensure even dimensions for H.264
                new_height = new_height - (new_height % 2)
                new_width = max_width - (max_width % 2)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            else:
                # Still ensure even dimensions
                new_width = img.width - (img.width % 2)
                new_height = img.height - (img.height % 2)
                if new_width != img.width or new_height != img.height:
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Save with sequential naming
            output_path = os.path.join(temp_dir, f"frame_{i:06d}.jpg")
            img.save(output_path, "JPEG", quality=90)
            frame_count += 1

        except Exception as e:
            log(f"Error processing {img_path}: {e}")
            continue

    return frame_count


def create_mp4_timelapse(
    images: List[str],
    output_path: str,
    fps: int = 24,
    max_width: int = 1280,
) -> Optional[str]:
    """Create an MP4 timelapse from images using ffmpeg.

    Args:
        images: List of image file paths
        output_path: Path to save the MP4
        fps: Frames per second
        max_width: Maximum width of output video

    Returns:
        Output path on success, None on failure
    """
    if not images:
        log("No images provided for timelapse")
        return None

    if len(images) < 2:
        log("Need at least 2 images for timelapse")
        return None

    log(f"Creating MP4 timelapse from {len(images)} images at {fps}fps")

    # Create temp directory for processed frames
    temp_dir = tempfile.mkdtemp(prefix="timelapse_")

    try:
        # Prepare frames
        frame_count = prepare_frames(images, temp_dir, max_width)

        if frame_count < 2:
            log("Not enough valid frames after processing")
            return None

        log(f"Prepared {frame_count} frames")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create MP4 with ffmpeg
        input_pattern = os.path.join(temp_dir, "frame_%06d.jpg")

        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-framerate",
            str(fps),
            "-i",
            input_pattern,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",  # Quality (lower = better, 18-28 is good range)
            "-pix_fmt",
            "yuv420p",  # Compatibility
            "-movflags",
            "+faststart",  # Web optimization
            output_path,
        ]

        log(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            log(f"ffmpeg error: {result.stderr}")
            return None

        # Get file size
        file_size = os.path.getsize(output_path)
        duration_sec = frame_count / fps

        log(
            f"Created {output_path}: {file_size / 1024 / 1024:.1f}MB, {duration_sec:.1f}s @ {fps}fps"
        )

        return output_path

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def create_daily_timelapse_mp4(target_frames: int = 60) -> Optional[str]:
    """Create a 4K daily timelapse MP4 from yesterday's daylight images.
    
    Saves to /app/data/www/timelapses/daily_YYYY-MM-DD.mp4
    
    Returns:
        Path to saved file, or None on failure
    """
    from datetime import date
    
    # Import from timelapse.py to get yesterday's daylight images
    try:
        from scripts.timelapse import get_yesterday_images
    except ImportError:
        from timelapse import get_yesterday_images
    
    images = get_yesterday_images()
    
    if not images:
        log("No daylight images found for daily MP4 timelapse")
        return None
    
    # Sample to target frame count
    sampled = sample_frames_evenly(images, target_frames)
    
    if len(sampled) < 2:
        log("Not enough daylight images for daily MP4 timelapse")
        return None
    
    yesterday = date.today() - timedelta(days=1)
    output_filename = f"daily_{yesterday.strftime('%Y-%m-%d')}.mp4"
    output_path = os.path.join(OUTPUT_ROOT, output_filename)
    
    log(f"Creating daily 4K timelapse for {yesterday} ({len(sampled)} frames)")
    
    # 4K at 24fps for smooth playback
    return create_mp4_timelapse(sampled, output_path, fps=24, max_width=4608)


def create_weekly_timelapse_mp4(target_frames: int = 200) -> Optional[str]:
    """Create a 4K weekly timelapse MP4 from the past 7 days.
    
    Saves to /app/data/www/timelapses/weekly_YYYY-Www.mp4
    
    Returns:
        Path to saved file, or None on failure
    """
    from datetime import date
    
    # Import from timelapse.py
    try:
        from scripts.timelapse import get_images_for_period
    except ImportError:
        from timelapse import get_images_for_period
    
    images = get_images_for_period(days=7)
    
    if not images:
        log("No images found for weekly MP4 timelapse")
        return None
    
    # Sample to target frame count
    sampled = sample_frames_evenly(images, target_frames)
    
    if len(sampled) < 2:
        log("Not enough images for weekly MP4 timelapse")
        return None
    
    today = date.today()
    week_num = today.isocalendar()[1]
    output_filename = f"weekly_{today.year}_W{week_num:02d}.mp4"
    output_path = os.path.join(OUTPUT_ROOT, output_filename)
    
    log(f"Creating weekly 4K timelapse for week {week_num} ({len(sampled)} frames)")
    
    # 4K at 24fps
    return create_mp4_timelapse(sampled, output_path, fps=24, max_width=4608)


def create_monthly_timelapse(
    year: Optional[int] = None,
    month: Optional[int] = None,
    target_frames: int = 500,
) -> Optional[str]:
    """Create a monthly timelapse MP4.

    By default, creates timelapse for the previous month.
    """
    if year is None or month is None:
        # Default to previous month
        today = datetime.now()
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        year = last_month.year
        month = last_month.month

    log(f"Creating monthly timelapse for {year}/{month:02d} ({target_frames} frames)")

    images = get_images_for_month(year, month)

    if not images:
        log(f"No images found for {year}/{month:02d}")
        return None

    # Sample to target frame count
    sampled = sample_frames_evenly(images, target_frames)

    # Output filename
    output_filename = f"monthly_{year}_{month:02d}.mp4"
    output_path = os.path.join(OUTPUT_ROOT, output_filename)

    return create_mp4_timelapse(sampled, output_path, fps=24, max_width=4608)


def create_yearly_timelapse(
    year: Optional[int] = None,
    target_frames: int = 4000,
) -> Optional[str]:
    """Create a yearly timelapse MP4.

    By default, creates timelapse for the previous year.
    """
    if year is None:
        year = datetime.now().year - 1

    log(f"Creating yearly timelapse for {year} (target: {target_frames} frames)")

    images = get_images_for_year(year)

    if not images:
        log(f"No images found for {year}")
        return None

    # Sample to target frame count (or use all if fewer)
    sampled = sample_frames_evenly(images, target_frames)

    # Output filename
    output_filename = f"yearly_{year}.mp4"
    output_path = os.path.join(OUTPUT_ROOT, output_filename)

    # 4K quality for yearly - 30fps for smoother playback
    return create_mp4_timelapse(sampled, output_path, fps=30, max_width=4608)


def get_timelapse_url(filename: str) -> str:
    """Get the Tailscale-accessible URL for a timelapse file."""
    tailscale_ip = os.getenv("TAILSCALE_IP", "100.94.172.114")
    web_port = os.getenv("WEB_PORT", "8080")
    return f"http://{tailscale_ip}:{web_port}/timelapses/{filename}"


def send_timelapse_notification(
    timelapse_type: str,
    filename: str,
    file_size_mb: float,
    duration_sec: float,
    frame_count: int,
) -> None:
    """Send email notification when a timelapse is ready for download.

    Only sends to joshcrow1193@gmail.com (not all recipients).
    """
    recipient = "joshcrow1193@gmail.com"

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", "Greenhouse Gazette <joshcrow1193@gmail.com>")

    if not smtp_user or not smtp_pass:
        log("SMTP credentials not configured, skipping notification")
        return

    url = get_timelapse_url(filename)
    tailscale_ip = os.getenv("TAILSCALE_IP", "100.94.172.114")

    subject = f"Timelapse Ready: {timelapse_type.title()} ({filename})"

    body = f"""Your {timelapse_type} timelapse is ready for download!

FILE DETAILS
------------
Filename: {filename}
Size: {file_size_mb:.1f} MB
Duration: {duration_sec:.1f} seconds
Frames: {frame_count}

HOW TO DOWNLOAD
---------------

Option 1: Direct Browser Download (Easiest)
  1. Make sure you're connected to Tailscale
  2. Open this URL in your browser:
     {url}
  3. The video will either play or download automatically

Option 2: Command Line (Mac/Linux)
  curl -O {url}

Option 3: SCP from Storyteller Pi
  scp joshcrow@{tailscale_ip}:/home/joshcrow/greenhouse-beach/data/www/timelapses/{filename} ~/Downloads/

BROWSE ALL TIMELAPSES
---------------------
  http://{tailscale_ip}:8080/timelapses/

---
The Greenhouse Gazette
"""

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log(f"Timelapse notification sent to {recipient}")
    except Exception as exc:  # noqa: BLE001
        log(f"Failed to send timelapse notification: {exc}")


def list_available_timelapses() -> List[dict]:
    """List all available timelapse files with metadata."""
    timelapses = []

    if not os.path.exists(OUTPUT_ROOT):
        return timelapses

    for filename in sorted(os.listdir(OUTPUT_ROOT)):
        if filename.endswith(".mp4"):
            filepath = os.path.join(OUTPUT_ROOT, filename)
            stat = os.stat(filepath)
            timelapses.append(
                {
                    "filename": filename,
                    "size_mb": stat.st_size / 1024 / 1024,
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": get_timelapse_url(filename),
                }
            )

    return timelapses


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extended timelapse generator")
    parser.add_argument("--type", choices=["monthly", "yearly", "list"], required=True)
    parser.add_argument("--year", type=int, help="Year for timelapse")
    parser.add_argument("--month", type=int, help="Month for monthly timelapse")
    parser.add_argument("--frames", type=int, help="Target frame count")

    args = parser.parse_args()

    if args.type == "list":
        timelapses = list_available_timelapses()
        if timelapses:
            print(f"\nAvailable timelapses ({len(timelapses)}):")
            for t in timelapses:
                print(f"  {t['filename']}: {t['size_mb']:.1f}MB - {t['url']}")
        else:
            print("No timelapses available")

    elif args.type == "monthly":
        frames = args.frames or 500
        result = create_monthly_timelapse(args.year, args.month, frames)
        if result:
            print(f"\nCreated: {result}")
            print(f"URL: {get_timelapse_url(os.path.basename(result))}")
        else:
            print("Failed to create monthly timelapse")

    elif args.type == "yearly":
        frames = args.frames or 4000
        result = create_yearly_timelapse(args.year, frames)
        if result:
            print(f"\nCreated: {result}")
            print(f"URL: {get_timelapse_url(os.path.basename(result))}")
        else:
            print("Failed to create yearly timelapse")
