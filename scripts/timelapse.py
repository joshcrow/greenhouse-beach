#!/usr/bin/env python3
"""Timelapse Generator for Greenhouse Gazette.

Creates animated GIFs from archived greenhouse images.
"""

import glob
import os
from datetime import datetime, timedelta
from typing import List, Optional
from PIL import Image
import io


def log(message: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [timelapse] {message}", flush=True)


ARCHIVE_ROOT = os.getenv("ARCHIVE_ROOT", "/app/data/archive")


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
) -> Optional[bytes]:
    """Create a looping GIF timelapse from a list of images.
    
    Args:
        images: List of image file paths
        output_path: Optional path to save the GIF
        max_frames: Maximum number of frames to include
        frame_duration_ms: Duration per frame in milliseconds
        max_width: Maximum width of output GIF
        max_height: Maximum height of output GIF
    
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
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize to fit within bounds while maintaining aspect ratio
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            frames.append(img)
        except Exception as e:
            log(f"Error processing {img_path}: {e}")
            continue
    
    if len(frames) < 2:
        log("Not enough valid frames for timelapse")
        return None
    
    log(f"Assembled {len(frames)} frames")
    
    # Create GIF in memory
    gif_buffer = io.BytesIO()
    
    # Save as GIF with looping
    frames[0].save(
        gif_buffer,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration_ms,
        loop=0,  # 0 = infinite loop
        optimize=True,
    )
    
    gif_bytes = gif_buffer.getvalue()
    log(f"Created timelapse GIF: {len(gif_bytes)} bytes")
    
    # Optionally save to file
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(gif_bytes)
        log(f"Saved timelapse to {output_path}")
    
    return gif_bytes


def create_weekly_timelapse() -> Optional[bytes]:
    """Create a timelapse GIF from the past week's images."""
    images = get_images_for_period(days=7)
    
    if not images:
        log("No images found for weekly timelapse")
        return None
    
    log(f"Found {len(images)} images from the past week")
    
    return create_timelapse_gif(
        images,
        max_frames=50,  # Reasonable size for email
        frame_duration_ms=150,  # Slightly faster for weekly
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
