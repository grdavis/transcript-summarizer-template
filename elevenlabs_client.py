"""ElevenLabs TTS client for generating audio briefings."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

import requests

# Brian — deep, resonant American male (ElevenLabs premade voice).
DEFAULT_VOICE_ID = "nPczCjzI2devNBz1zQrb"

# Always request natural-speed audio from ElevenLabs; speed up locally with ffmpeg.
ELEVENLABS_SPEECH_SPEED = 1.0

# Post-process ElevenLabs MP3 with ffmpeg atempo (default 1.5x playback).
DEFAULT_AUDIO_TEMPO = 1.5
MIN_AUDIO_TEMPO = 0.5
MAX_AUDIO_TEMPO = 2.0


def get_api_key() -> str | None:
    return os.environ.get("ELEVENLABS_API_KEY", "").strip() or None


def get_audio_tempo() -> float:
    """Return ffmpeg atempo multiplier applied to the ElevenLabs MP3 (default 1.5)."""
    raw = os.environ.get("AUDIO_TEMPO", "").strip()
    if not raw:
        return DEFAULT_AUDIO_TEMPO
    try:
        tempo = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"AUDIO_TEMPO must be a number between {MIN_AUDIO_TEMPO} and {MAX_AUDIO_TEMPO}, got {raw!r}"
        ) from exc
    if not MIN_AUDIO_TEMPO <= tempo <= MAX_AUDIO_TEMPO:
        raise ValueError(
            f"AUDIO_TEMPO must be between {MIN_AUDIO_TEMPO} and {MAX_AUDIO_TEMPO}, got {tempo}"
        )
    return tempo


def clean_for_tts(markdown: str) -> str:
    """Remove markdown symbols so TTS sounds more natural."""
    text = markdown.replace("*", "")
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def speed_up_audio(mp3_bytes: bytes, tempo: float) -> bytes:
    """Time-compress MP3 audio without changing pitch using ffmpeg atempo."""
    if tempo == 1.0:
        return mp3_bytes

    with tempfile.NamedTemporaryFile(suffix=".mp3") as input_file, tempfile.NamedTemporaryFile(
        suffix=".mp3"
    ) as output_file:
        input_file.write(mp3_bytes)
        input_file.flush()

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_file.name,
                "-filter:a",
                f"atempo={tempo}",
                "-vn",
                output_file.name,
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg atempo failed: {stderr or 'unknown error'}")

        output_file.seek(0)
        return output_file.read()


def generate_audio(text: str, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
    """
    Generate an MP3 audio file from text using ElevenLabs API.
    Defaults to the "Brian" voice and the `eleven_turbo_v2_5` model.
    ElevenLabs renders at 1.0x; ffmpeg atempo (default 1.5) sets final playback speed.
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

    tempo = get_audio_tempo()

    data = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5,
            "speed": ELEVENLABS_SPEECH_SPEED,
        },
    }

    print(
        f"Generating audio with ElevenLabs (voice speed={ELEVENLABS_SPEECH_SPEED}, "
        f"playback tempo={tempo}x)..."
    )
    response = requests.post(url, json=data, headers=headers)

    if not response.ok:
        try:
            err_detail = response.json()
            print(f"ElevenLabs Error: {err_detail}")
        except Exception:
            pass
        response.raise_for_status()

    mp3_bytes = response.content
    if tempo != 1.0:
        mp3_bytes = speed_up_audio(mp3_bytes, tempo)

    print("Audio generation complete.")
    return mp3_bytes
