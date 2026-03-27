"""Tests for SessionOutputManager — directory creation and path construction."""
from __future__ import annotations

import re

import pytest

from ofp_playground.config.output import SessionOutputManager


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    """SessionOutputManager rooted inside tmp_path."""
    monkeypatch.chdir(tmp_path)
    return SessionOutputManager("conv:abc12345")


class TestInit:
    def test_root_created_on_init(self, mgr):
        assert mgr.root.exists()
        assert mgr.root.is_dir()

    def test_root_under_result(self, mgr):
        assert mgr.root.name.startswith("20")
        assert mgr.root.parent.name == "result"

    def test_timestamp_in_root_name(self, mgr):
        # Root name should match YYYYMMDD_HHMMSS_SLUG pattern
        assert re.match(r"\d{8}_\d{6}_", mgr.root.name)

    def test_slug_from_conv_id(self, mgr):
        # "conv:abc12345" → last segment before colon trimmed to 8 chars
        assert "abc12345" in mgr.root.name

    def test_special_chars_sanitised(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mgr = SessionOutputManager("conv:my/weird$name!")
        assert mgr.root.exists()

    def test_empty_conv_id_uses_session_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mgr = SessionOutputManager("conv:")  # empty slug after split
        assert mgr.root.exists()


class TestSubdirectories:
    def test_images_created_lazily(self, mgr):
        assert not (mgr.root / "images").exists()  # not created yet
        images = mgr.images
        assert images.exists() and images.is_dir()

    def test_videos_created_lazily(self, mgr):
        videos = mgr.videos
        assert videos.exists() and videos.is_dir()

    def test_music_created_lazily(self, mgr):
        music = mgr.music
        assert music.exists() and music.is_dir()

    def test_web_created_lazily(self, mgr):
        web = mgr.web
        assert web.exists() and web.is_dir()

    def test_breakout_created_lazily(self, mgr):
        breakout = mgr.breakout
        assert breakout.exists() and breakout.is_dir()

    def test_images_are_under_root(self, mgr):
        assert mgr.images.parent == mgr.root

    def test_videos_are_under_root(self, mgr):
        assert mgr.videos.parent == mgr.root

    def test_idempotent_access(self, mgr):
        """Accessing the same property twice is safe (mkdir exist_ok=True)."""
        _ = mgr.images
        _ = mgr.images  # second access – should not raise

    def test_all_subdirs_under_root(self, mgr):
        dirs = [mgr.images, mgr.videos, mgr.music, mgr.web, mgr.breakout]
        for d in dirs:
            assert d.parent == mgr.root

    def test_root_property_returns_path(self, mgr):
        from pathlib import Path
        assert isinstance(mgr.root, Path)
