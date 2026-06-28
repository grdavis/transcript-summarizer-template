"""ElevenLabs TTS client for generating audio briefings."""

from __future__ import annotations

import os
import re

import requests


def get_api_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip() or None


def clean_for_tts(markdown: str) -> str:
    """Remove markdown symbols so TTS sounds more natural."""
    text = markdown.replace("*", "")
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def generate_audio(text: str, voice_id: str = "N2lVS1w4EtoT3dr4eOWO") -> bytes:
    """
    Generate an MP3 audio file from text using ElevenLabs API.
    Defaults to the "Callum" voice and the `eleven_turbo_v2_5` model.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY must be set to generate audio briefings")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }

    data = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5,
        },
    }

    print("Generating audio with ElevenLabs...")
    response = requests.post(url, json=data, headers=headers)

    if not response.ok:
        try:
            err_detail = response.json()
            print(f"ElevenLabs Error: {err_detail}")
        except Exception:
            pass
        response.raise_for_status()

    print("Audio generation complete.")
    return response.content
