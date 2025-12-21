"""
Unit tests for curator.py
"""

import os
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

import curator


class TestListCandidateFiles:
    """Tests for list_candidate_files() function."""

    @pytest.mark.unit
    def test_finds_jpg_files(self, tmp_path, monkeypatch):
        """Should find .jpg files in directory."""
        (tmp_path / "image1.jpg").touch()
        (tmp_path / "image2.jpg").touch()
        (tmp_path / "image3.png").touch()  # Should also be found (png is valid)
        
        # Patch the module constant
        monkeypatch.setattr(curator, "INCOMING_DIR", str(tmp_path))

        result = curator.list_candidate_files()

        assert len(result) == 3  # jpg, jpg, and png

    @pytest.mark.unit
    def test_skips_tmp_files(self, tmp_path, monkeypatch):
        """Should skip .tmp files."""
        (tmp_path / "image.jpg").touch()
        (tmp_path / "image.tmp").touch()
        
        monkeypatch.setattr(curator, "INCOMING_DIR", str(tmp_path))

        result = curator.list_candidate_files()

        assert len(result) == 1
        # Check the filename ends with .jpg, not .tmp
        assert result[0].endswith(".jpg")

    @pytest.mark.unit
    def test_handles_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty list for empty directory."""
        monkeypatch.setattr(curator, "INCOMING_DIR", str(tmp_path))
        
        result = curator.list_candidate_files()
        assert result == []

    @pytest.mark.unit
    def test_handles_nonexistent_directory(self, monkeypatch):
        """Should return empty list for non-existent directory."""
        monkeypatch.setattr(curator, "INCOMING_DIR", "/nonexistent/path")
        
        result = curator.list_candidate_files()
        assert result == []


class TestArchivePathFor:
    """Tests for archive_path_for() function."""

    @pytest.mark.unit
    def test_creates_dated_path(self, tmp_path, monkeypatch):
        """Should create date-based archive path."""
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        result = curator.archive_path_for("/app/data/incoming/test.jpg")

        now = datetime.utcnow()
        assert str(now.year) in result
        assert f"{now.month:02d}" in result
        assert f"{now.day:02d}" in result
        assert result.endswith("test.jpg")

    @pytest.mark.unit
    def test_preserves_filename(self, tmp_path, monkeypatch):
        """Should preserve original filename."""
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        result = curator.archive_path_for("/app/data/incoming/my_image.jpg")
        assert "my_image.jpg" in result


class TestProcessFile:
    """Tests for process_file() function."""

    @pytest.mark.unit
    def test_accepts_valid_brightness(self, tmp_path, monkeypatch):
        """Should archive images with valid brightness."""
        import cv2
        # Create a gray image (brightness ~128)
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        img_path = tmp_path / "test.jpg"
        cv2.imwrite(str(img_path), img)

        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))
        
        # Image should be moved (not deleted)
        assert not img_path.exists()
        # Should be archived somewhere
        archived_files = list(archive_root.rglob("*.jpg"))
        assert len(archived_files) == 1

    @pytest.mark.unit
    def test_rejects_dark_image(self, tmp_path, monkeypatch):
        """Should archive pitch-black images for forensic value."""
        import cv2
        img = np.full((100, 100, 3), 5, dtype=np.uint8)  # Very dark
        img_path = tmp_path / "dark.jpg"
        cv2.imwrite(str(img_path), img)
        
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))

        assert not img_path.exists()  # Should be moved
        archived_files = list((archive_root / "_night").rglob("*.jpg"))
        assert len(archived_files) == 1

    @pytest.mark.unit
    def test_rejects_overexposed_image(self, tmp_path, monkeypatch):
        """Should delete images that are overexposed."""
        import cv2
        img = np.full((100, 100, 3), 252, dtype=np.uint8)  # Very bright
        img_path = tmp_path / "bright.jpg"
        cv2.imwrite(str(img_path), img)
        
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))

        assert not img_path.exists()  # Should be deleted

    @pytest.mark.unit
    def test_handles_corrupt_image(self, tmp_path, monkeypatch):
        """Should delete corrupt/unreadable images."""
        img_path = tmp_path / "corrupt.jpg"
        img_path.write_bytes(b"not a valid image")
        
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))

        assert not img_path.exists()  # Should be deleted

    @pytest.mark.unit
    def test_handles_nonexistent_file(self, monkeypatch, tmp_path):
        """Should handle non-existent file gracefully."""
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))
        
        # Should not raise
        curator.process_file("/nonexistent/file.jpg")


class TestLuminanceThresholds:
    """Tests for luminance threshold constants."""

    @pytest.mark.unit
    def test_low_threshold_allows_dim_images(self, tmp_path, monkeypatch):
        """Luminance threshold should allow dim (but not black) images."""
        import cv2
        # Create image at threshold boundary (luminance ~15)
        img = np.full((100, 100, 3), 15, dtype=np.uint8)
        img_path = tmp_path / "dim.jpg"
        cv2.imwrite(str(img_path), img)
        
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))
        
        # Should be archived (above threshold of 10)
        archived_files = list(archive_root.rglob("*.jpg"))
        assert len(archived_files) == 1

    @pytest.mark.unit
    def test_high_threshold_allows_bright_images(self, tmp_path, monkeypatch):
        """Luminance threshold should allow bright (but not overexposed) images."""
        import cv2
        # Create image at threshold boundary (luminance ~245)
        img = np.full((100, 100, 3), 245, dtype=np.uint8)
        img_path = tmp_path / "bright.jpg"
        cv2.imwrite(str(img_path), img)
        
        archive_root = tmp_path / "archive"
        archive_root.mkdir()
        monkeypatch.setattr(curator, "ARCHIVE_ROOT", str(archive_root))

        curator.process_file(str(img_path))
        
        # Should be archived (below threshold of 250)
        archived_files = list(archive_root.rglob("*.jpg"))
        assert len(archived_files) == 1
