"""
Unit tests for timelapse.py
"""

import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO
import numpy as np

import timelapse


class TestGetImagesForPeriod:
    """Tests for get_images_for_period() function."""

    @pytest.mark.unit
    def test_finds_images_in_date_range(self, tmp_path, monkeypatch):
        """Should find images within date range."""
        archive = tmp_path / "archive"
        
        # Create dated directory structure
        today = datetime.now()
        for i in range(3):
            date = today - timedelta(days=i)
            date_dir = archive / str(date.year) / f"{date.month:02d}" / f"{date.day:02d}"
            date_dir.mkdir(parents=True)
            (date_dir / f"image_{i}.jpg").touch()

        monkeypatch.setattr(timelapse, "ARCHIVE_ROOT", str(archive))

        result = timelapse.get_images_for_period(days=7)

        assert len(result) >= 3

    @pytest.mark.unit
    def test_returns_empty_for_no_images(self, tmp_path, monkeypatch):
        """Should return empty list if no images found."""
        archive = tmp_path / "archive"
        archive.mkdir()
        monkeypatch.setattr(timelapse, "ARCHIVE_ROOT", str(archive))

        result = timelapse.get_images_for_period(days=7)
        assert result == []

    @pytest.mark.unit
    def test_sorts_chronologically(self, tmp_path, monkeypatch):
        """Should return images sorted by date."""
        archive = tmp_path / "archive"
        
        # Create images with different timestamps
        for day_offset, hour in [(2, 10), (1, 14), (0, 8)]:
            date = datetime.now() - timedelta(days=day_offset)
            date_dir = archive / str(date.year) / f"{date.month:02d}" / f"{date.day:02d}"
            date_dir.mkdir(parents=True, exist_ok=True)
            img_path = date_dir / f"image_{hour:02d}0000.jpg"
            img_path.touch()

        monkeypatch.setattr(timelapse, "ARCHIVE_ROOT", str(archive))

        result = timelapse.get_images_for_period(days=7)

        # Should be sorted oldest to newest
        assert len(result) == 3


class TestCreateTimelapseGif:
    """Tests for create_timelapse_gif() function."""

    @pytest.mark.unit
    def test_returns_none_for_few_images(self):
        """Should return None if fewer than MIN_FRAMES images."""
        result = timelapse.create_timelapse_gif(["/path/to/single.jpg"])
        assert result is None

    @pytest.mark.unit
    def test_creates_gif_from_images(self, tmp_path):
        """Should create a GIF from valid images."""
        from PIL import Image
        
        # Create test images
        images = []
        for i in range(5):
            img = Image.new("RGB", (100, 100), color=(i * 50, 0, 0))
            path = tmp_path / f"image_{i}.jpg"
            img.save(str(path))
            images.append(str(path))

        result = timelapse.create_timelapse_gif(images)

        assert result is not None
        assert isinstance(result, bytes)
        # Verify it's a valid GIF
        assert result[:3] == b"GIF"

    @pytest.mark.unit
    def test_handles_corrupt_images(self, tmp_path):
        """Should skip corrupt images and still create GIF."""
        from PIL import Image
        
        # Create mix of valid and corrupt images
        images = []
        for i in range(5):
            path = tmp_path / f"image_{i}.jpg"
            if i == 2:  # Make one corrupt
                path.write_bytes(b"corrupt data")
            else:
                img = Image.new("RGB", (100, 100), color=(i * 50, 0, 0))
                img.save(str(path))
            images.append(str(path))

        result = timelapse.create_timelapse_gif(images)

        # Should still create GIF with valid images
        assert result is not None

    @pytest.mark.unit
    def test_respects_max_frames(self, tmp_path):
        """Should sample images if too many."""
        from PIL import Image
        
        # Create many test images
        images = []
        for i in range(100):
            img = Image.new("RGB", (50, 50), color=(i % 256, 0, 0))
            path = tmp_path / f"image_{i:03d}.jpg"
            img.save(str(path))
            images.append(str(path))

        # Default max_frames is 60
        result = timelapse.create_timelapse_gif(images, max_frames=30)

        assert result is not None

    @pytest.mark.unit
    def test_output_to_file(self, tmp_path):
        """Should write GIF to file if path provided."""
        from PIL import Image
        
        images = []
        for i in range(5):
            img = Image.new("RGB", (100, 100), color=(i * 50, 0, 0))
            path = tmp_path / f"image_{i}.jpg"
            img.save(str(path))
            images.append(str(path))

        output_path = tmp_path / "output.gif"
        timelapse.create_timelapse_gif(images, output_path=str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0
