"""Tests for ElevenLabs TTS helpers."""

from __future__ import annotations

from elevenlabs_client import clean_for_tts, get_api_key


def test_clean_for_tts_strips_markdown():
    markdown = "## Top stories\n\n**Bold** and [a link](https://example.com)."
    cleaned = clean_for_tts(markdown)
    assert "##" not in cleaned
    assert "**" not in cleaned
    assert "Top stories" in cleaned
    assert "Bold" in cleaned
    assert "a link" in cleaned
    assert "https://example.com" not in cleaned


def test_get_api_key_missing(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert get_api_key() is None


def test_get_api_key_present(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    assert get_api_key() == "test-key"
