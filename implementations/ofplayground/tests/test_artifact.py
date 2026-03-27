"""Tests for Utterance and ArtifactFeature — the core typed data model."""
from __future__ import annotations

import time

import pytest

from ofp_playground.models.artifact import ArtifactFeature, Utterance


# ---------------------------------------------------------------------------
# ArtifactFeature
# ---------------------------------------------------------------------------

class TestArtifactFeature:
    def test_basic_fields(self):
        af = ArtifactFeature(
            feature_key="text",
            mime_type="text/plain",
            value="hello",
        )
        assert af.feature_key == "text"
        assert af.mime_type == "text/plain"
        assert af.value == "hello"
        assert af.value_url is None

    def test_value_url(self):
        af = ArtifactFeature(
            feature_key="image",
            mime_type="image/png",
            value_url="/tmp/img.png",
        )
        assert af.value is None
        assert af.value_url == "/tmp/img.png"

    def test_both_value_and_url(self):
        af = ArtifactFeature(
            feature_key="text",
            mime_type="text/plain",
            value="inline",
            value_url="https://example.com/text.txt",
        )
        assert af.value == "inline"
        assert af.value_url == "https://example.com/text.txt"


# ---------------------------------------------------------------------------
# Utterance.from_text
# ---------------------------------------------------------------------------

class TestUtteranceFromText:
    def test_basic_construction(self):
        u = Utterance.from_text("tag:test:alice", "Alice", "Hello!")
        assert u.speaker_uri == "tag:test:alice"
        assert u.speaker_name == "Alice"
        assert u.text == "Hello!"

    def test_only_text_feature(self):
        u = Utterance.from_text("tag:test:a", "A", "Test")
        assert set(u.features.keys()) == {"text"}

    def test_text_feature_fields(self):
        u = Utterance.from_text("tag:test:a", "A", "Test content")
        feat = u.features["text"]
        assert feat.feature_key == "text"
        assert feat.mime_type == "text/plain"
        assert feat.value == "Test content"

    def test_timestamp_recent(self):
        before = time.time()
        u = Utterance.from_text("tag:test:a", "A", "msg")
        after = time.time()
        assert before <= u.timestamp <= after

    def test_empty_text(self):
        u = Utterance.from_text("tag:test:a", "A", "")
        assert u.text == ""


# ---------------------------------------------------------------------------
# Utterance.from_image
# ---------------------------------------------------------------------------

class TestUtteranceFromImage:
    def test_has_text_and_image_features(self):
        u = Utterance.from_image("tag:test:p", "Painter", "A sunset", "/tmp/img.png")
        assert "text" in u.features
        assert "image" in u.features

    def test_text_description_stored(self):
        u = Utterance.from_image("tag:test:p", "Painter", "A sunset", "/tmp/img.png")
        assert u.text == "A sunset"

    def test_image_path_in_value_url(self):
        u = Utterance.from_image("tag:test:p", "Painter", "desc", "/tmp/img.png")
        assert u.features["image"].value_url == "/tmp/img.png"

    def test_image_mime_type(self):
        u = Utterance.from_image("tag:test:p", "Painter", "desc", "/tmp/img.png")
        assert "image" in u.features["image"].mime_type


# ---------------------------------------------------------------------------
# Utterance.from_video
# ---------------------------------------------------------------------------

class TestUtteranceFromVideo:
    def test_from_video_exists(self):
        # Ensure the factory is present (may be similar to from_image)
        assert hasattr(Utterance, "from_video")

    def test_from_video_basic(self):
        u = Utterance.from_video("tag:test:v", "Videographer", "A timelapse", "/tmp/vid.mp4")
        assert u.text == "A timelapse"
        assert "video" in u.features
        assert u.features["video"].value_url == "/tmp/vid.mp4"


# ---------------------------------------------------------------------------
# Utterance.text property
# ---------------------------------------------------------------------------

class TestUtteranceTextProperty:
    def test_returns_text_feature_value(self):
        u = Utterance.from_text("tag:test:a", "A", "Hello world")
        assert u.text == "Hello world"

    def test_missing_text_feature_returns_empty(self):
        u = Utterance(
            speaker_uri="tag:test:a",
            speaker_name="A",
            features={},  # no "text" key
        )
        assert u.text == ""

    def test_text_feature_with_none_value_returns_empty(self):
        u = Utterance(
            speaker_uri="tag:test:a",
            speaker_name="A",
            features={
                "text": ArtifactFeature(feature_key="text", mime_type="text/plain", value=None)
            },
        )
        assert u.text == ""


# ---------------------------------------------------------------------------
# Utterance.primary_media property
# ---------------------------------------------------------------------------

class TestPrimaryMedia:
    def test_no_media_returns_none(self):
        u = Utterance.from_text("tag:test:a", "A", "plain text")
        assert u.primary_media is None

    def test_image_is_primary_media(self):
        u = Utterance.from_image("tag:test:p", "P", "desc", "/img.png")
        media = u.primary_media
        assert media is not None
        assert media.feature_key == "image"

    def test_video_is_primary_media(self):
        u = Utterance.from_video("tag:test:v", "V", "desc", "/vid.mp4")
        media = u.primary_media
        assert media is not None
        assert media.feature_key == "video"

    def test_text_not_returned_as_primary(self):
        u = Utterance.from_text("tag:test:a", "A", "text only")
        assert u.primary_media is None

    def test_custom_feature_returned(self):
        u = Utterance(
            speaker_uri="tag:test:a",
            speaker_name="A",
            features={
                "text": ArtifactFeature("text", "text/plain", value="desc"),
                "3d": ArtifactFeature("3d", "model/gltf", value_url="/model.glb"),
            },
        )
        media = u.primary_media
        assert media is not None
        assert media.feature_key == "3d"
