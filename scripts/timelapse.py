#!/usr/bin/env python3
"""Timelapse Generator for Greenhouse Gazette.

Creates animated GIFs from archived greenhouse images.
"""

import glob
import io
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional

import requests
from PIL import Image

from utils.logger import create_logger
from utils.image_utils import sample_frames_evenly


log = create_logger("timelapse")


ARCHIVE_ROOT = os.getenv("ARCHIVE_ROOT", "/app/data/archive")


def get_sunrise_sunset(target_date: datetime) -> tuple[datetime, datetime]:
    """Get sunrise and sunset times for a specific date using OpenWeather API."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    lat = os.getenv("LAT")
    lon = os.getenv("LON")

    if not api_key or not lat or not lon:
        log("Weather API config missing, using approximate daylight hours")
        # Use approximate daylight hours (7 AM to 6 PM) for the target date
        sunrise = target_date.replace(hour=7, minute=0, second=0, microsecond=0)
        sunset = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
        return sunrise, sunset

    try:
        # Get weather data - we'll use current data as approximation for any date
        url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "exclude": "minutely,hourly,alerts",
        }

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        daily_list = data.get("daily", [])

        if daily_list:
            # Use today's data as approximation for the target date
            first = daily_list[0] or {}
            sunrise_ts = first.get("sunrise")
            sunset_ts = first.get("sunset")

            if sunrise_ts and sunset_ts:
                # Apply the sunrise/sunset times to the target date
                sunrise_today = datetime.fromtimestamp(sunrise_ts)
                sunset_today = datetime.fromtimestamp(sunset_ts)

                # Create sunrise/sunset for the target date with today's times
                sunrise = target_date.replace(
                    hour=sunrise_today.hour,
                    minute=sunrise_today.minute,
                    second=sunrise_today.second,
                    microsecond=0,
                )
                sunset = target_date.replace(
                    hour=sunset_today.hour,
                    minute=sunset_today.minute,
                    second=sunset_today.second,
                    microsecond=0,
                )

                log(
                    f"Daylight hours for {target_date.strftime('%Y-%m-%d')}: {sunrise.strftime('%H:%M')} - {sunset.strftime('%H:%M')}"
                )
                return sunrise, sunset

    except Exception as e:
        log(f"Error fetching sunrise/sunset: {e}")

    # Fallback to approximate times for the target date
    sunrise = target_date.replace(hour=7, minute=0, second=0, microsecond=0)
    sunset = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
    return sunrise, sunset


def extract_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract timestamp from image filename like 'img_camera_20251219_154635.jpg'."""
    match = re.search(r"(\d{8})_(\d{6})", filename)
    if match:
        date_str, time_str = match.groups()
        try:
            return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
        except ValueError:
            return None
    return None


def is_daylight_image(image_path: str, sunrise: datetime, sunset: datetime) -> bool:
    """Check if an image was captured during daylight hours."""
    timestamp = extract_timestamp_from_filename(os.path.basename(image_path))
    if not timestamp:
        return True  # Include if we can't determine time

    # Convert to local timezone comparison
    return sunrise <= timestamp <= sunset


def get_yesterday_images() -> List[str]:
    """Get all images from yesterday, filtered for daylight hours."""
    yesterday = datetime.now() - timedelta(days=1)
    year = yesterday.strftime("%Y")
    month = yesterday.strftime("%m")
    day = yesterday.strftime("%d")

    day_path = os.path.join(ARCHIVE_ROOT, year, month, day)
    if not os.path.exists(day_path):
        log(f"No archive directory for yesterday: {day_path}")
        return []

    # Get all images from yesterday
    images = glob.glob(os.path.join(day_path, "*.jpg"))
    images.sort()

    log(f"Found {len(images)} total images from yesterday ({year}/{month}/{day})")

    # Get daylight hours for yesterday
    sunrise, sunset = get_sunrise_sunset(yesterday)

    # Filter for daylight images
    daylight_images = []
    for img_path in images:
        if is_daylight_image(img_path, sunrise, sunset):
            daylight_images.append(img_path)

    log(f"Filtered to {len(daylight_images)} daylight images")
    return daylight_images


# sample_frames_evenly imported from utils.image_utils


def get_images_for_period(days: int = 7) -> List[str]:
    """Get all images from the last N days, sorted chronologically."""
    images = []
    now = datetime.now()

    for i in range(days, -1, -1):  # Go from oldest to newest
        date = now - timedelta(days=i)
        year = date.strftime("%Y")
        month = date.strftime("%m")
        day = date.strftime("%d")

        day_path = os.path.join(ARCHIVE_ROOT, year, month, day)
        if os.path.exists(day_path):
            day_images = glob.glob(os.path.join(day_path, "*.jpg"))
            # Sort by filename (contains timestamp)
            day_images.sort()
            images.extend(day_images)

    return images


def create_timelapse_gif(
    images: List[str],
    output_path: Optional[str] = None,
    max_frames: int = 50,
    frame_duration_ms: int = 200,
    max_width: int = 600,
    max_height: int = 400,
    optimize: bool = True,
    colors: int = 256,
) -> Optional[bytes]:
    """Create a looping GIF timelapse from a list of images.

    Args:
        images: List of image file paths
        output_path: Optional path to save the GIF
        max_frames: Maximum number of frames to include
        frame_duration_ms: Duration per frame in milliseconds
        max_width: Maximum width of output GIF
        max_height: Maximum height of output GIF
        optimize: Whether to apply optimization
        colors: Maximum number of colors for quantization

    Returns:
        GIF bytes, or None on failure
    """
    if not images:
        log("No images provided for timelapse")
        return None

    # Sample images evenly if we have too many
    if len(images) > max_frames:
        step = len(images) / max_frames
        indices = [int(i * step) for i in range(max_frames)]
        images = [images[i] for i in indices]

    log(f"Creating timelapse from {len(images)} images")

    frames = []
    for img_path in images:
        try:
            img = Image.open(img_path)

            # Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Force resize to max_width while maintaining aspect ratio
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Also enforce max_height if needed
            if img.height > max_height:
                ratio = max_height / img.height
                new_width = int(img.width * ratio)
                img = img.resize((new_width, max_height), Image.Resampling.LANCZOS)

            frames.append(img)
        except Exception as e:
            log(f"Error processing {img_path}: {e}")
            continue

    if len(frames) < 2:
        log("Not enough valid frames for timelapse")
        return None

    log(f"Assembled {len(frames)} frames (target size: {max_width}px wide)")

    # Create GIF in memory
    gif_buffer = io.BytesIO()

    # Save as GIF with optimization
    save_kwargs = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "duration": frame_duration_ms,
        "loop": 0,  # 0 = infinite loop
    }

    if optimize:
        save_kwargs["optimize"] = True
        save_kwargs["colors"] = colors

    frames[0].save(gif_buffer, **save_kwargs)

    gif_bytes = gif_buffer.getvalue()
    log(
        f"Created timelapse GIF: {len(gif_bytes)} bytes ({len(gif_bytes) / 1024 / 1024:.1f}MB)"
    )

    # Optionally save to file
    if output_path:
        with open(output_path, "wb") as f:
            f.write(gif_bytes)
        log(f"Saved timelapse to {output_path}")

    return gif_bytes


def create_daily_timelapse() -> Optional[bytes]:
    """Create a daily timelapse GIF from yesterday's daylight images.

    This function:
    - Gets all images from yesterday (00:00 to 23:59)
    - Filters for daylight hours only
    - Samples up to 60 frames for smooth animation
    - Optimizes for email delivery
    """
    log("Creating daily timelapse from yesterday's images...")

    # Get yesterday's daylight images
    daylight_images = get_yesterday_images()

    if not daylight_images:
        log("No daylight images found for daily timelapse")
        return None

    # Sample frames for smooth animation
    target_frames = 60
    sampled_images = sample_frames_evenly(daylight_images, target_frames)

    if len(sampled_images) < 2:
        log("Not enough daylight images for daily timelapse")
        return None

    # Create optimized GIF with specific parameters for daily use
    return create_timelapse_gif(
        sampled_images,
        max_frames=60,  # 60 frames for 6-second animation
        frame_duration_ms=100,  # 10 fps
        max_width=600,  # Force 600px width for size management
        max_height=400,
        optimize=True,
        colors=128,  # Aggressive color quantization for smaller file size
    )


def create_weekly_timelapse() -> Optional[bytes]:
    """Create a timelapse GIF from the past week's images."""
    images = get_images_for_period(days=7)

    if not images:
        log("No images found for weekly timelapse")
        return None

    log(f"Found {len(images)} images from the past week")

    return create_timelapse_gif(
        images,
        max_frames=100,  # 100 frames for weekly edition
        frame_duration_ms=100,  # 10 fps for 10-second animation
        max_width=600,
        max_height=400,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Number of days to include")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--test", action="store_true", help="Test run")
    args = parser.parse_args()

    images = get_images_for_period(args.days)
    print(f"Found {len(images)} images")

    if args.test:
        for img in images[:5]:
            print(f"  - {img}")
        if len(images) > 5:
            print(f"  ... and {len(images) - 5} more")
    else:
        output = args.output or "/tmp/timelapse.gif"
        gif_bytes = create_timelapse_gif(images, output_path=output)
        if gif_bytes:
            print(f"Created {output} ({len(gif_bytes)} bytes)")
