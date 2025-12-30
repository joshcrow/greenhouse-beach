"""Shared image utilities for Greenhouse Gazette scripts.

Provides common image processing functions used by timelapse generators.

Usage:
    from utils.image_utils import sample_frames_evenly
    
    # Sample 50 frames evenly from a list of 500 images
    frames = sample_frames_evenly(all_images, target_count=50)
"""

from typing import List

from utils.logger import create_logger

log = create_logger("image_utils")


def sample_frames_evenly(images: List[str], target_count: int) -> List[str]:
    """Sample frames evenly from an image list to reach target count.
    
    Selects frames at regular intervals to create an even distribution
    across the timeline, useful for creating smooth timelapses.
    
    Args:
        images: List of image file paths (sorted chronologically)
        target_count: Desired number of frames in output
    
    Returns:
        List of sampled image paths, or original list if already <= target_count
    """
    if len(images) <= target_count:
        return images

    step = len(images) / target_count
    indices = [int(i * step) for i in range(target_count)]
    sampled = [images[i] for i in indices]

    log(f"Sampled {len(sampled)} frames from {len(images)} images")
    return sampled
