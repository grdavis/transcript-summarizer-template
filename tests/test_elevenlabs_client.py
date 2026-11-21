from unittest.mock import MagicMock, patch

import pytest

from elevenlabs_client import (
    DEFAULT_AUDIO_TEMPO,
    DEFAULT_VOICE_ID,
    ELEVENLABS_SPEECH_SPEED,
    generate_audio,
    get_audio_tempo,
    speed_up_audio,
)


def test_default_voice_is_brian():
    assert DEFAULT_VOICE_ID == "nPczCjzI2devNBz1zQrb"


def test_get_audio_tempo_defaults_to_one_point_five(monkeypatch):
    monkeypatch.delenv("AUDIO_TEMPO", raising=False)
    assert get_audio_tempo() == DEFAULT_AUDIO_TEMPO


def test_get_audio_tempo_reads_env_override(monkeypatch):
    monkeypatch.setenv("AUDIO_TEMPO", "1.2")
    assert get_audio_tempo() == 1.2


def test_get_audio_tempo_rejects_out_of_range(monkeypatch):
    monkeypatch.setenv("AUDIO_TEMPO", "3")
    with pytest.raises(ValueError, match="AUDIO_TEMPO must be between"):
        get_audio_tempo()


def test_get_audio_tempo_rejects_non_numeric(monkeypatch):
    monkeypatch.setenv("AUDIO_TEMPO", "fast")
    with pytest.raises(ValueError, match="AUDIO_TEMPO must be a number"):
        get_audio_tempo()


@patch("elevenlabs_client.get_api_key", return_value="test-key")
@patch("elevenlabs_client.get_audio_tempo", return_value=1.5)
@patch("elevenlabs_client.speed_up_audio", return_value=b"fast-mp3")
@patch("elevenlabs_client.requests.post")
def test_generate_audio_uses_brian_at_one_x_and_applies_playback_tempo(
    mock_post, mock_speed_up, _mock_tempo, _mock_key
):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.content = b"raw-mp3"
    mock_post.return_value = mock_response

    result = generate_audio("Hello briefing")

    assert result == b"fast-mp3"
    assert mock_post.call_args.args[0].endswith(DEFAULT_VOICE_ID)
    payload = mock_post.call_args.kwargs["json"]
    assert payload["voice_settings"]["speed"] == ELEVENLABS_SPEECH_SPEED
    mock_speed_up.assert_called_once_with(b"raw-mp3", 1.5)


@patch("elevenlabs_client.get_api_key", return_value="test-key")
@patch("elevenlabs_client.get_audio_tempo", return_value=1.0)
@patch("elevenlabs_client.speed_up_audio")
@patch("elevenlabs_client.requests.post")
def test_generate_audio_skips_ffmpeg_when_tempo_is_one(
    mock_post, mock_speed_up, _mock_tempo, _mock_key
):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.content = b"raw-mp3"
    mock_post.return_value = mock_response

    result = generate_audio("Hello briefing")

    assert result == b"raw-mp3"
    mock_speed_up.assert_not_called()


@patch("elevenlabs_client.subprocess.run")
def test_speed_up_audio_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)

    class FakeTempFile:
        def __init__(self, **_kwargs):
            self.name = "/tmp/fake.mp3"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def write(self, _data):
            return None

        def flush(self):
            return None

        def seek(self, _pos):
            return None

        def read(self):
            return b"output-mp3"

    with patch("elevenlabs_client.tempfile.NamedTemporaryFile", FakeTempFile):
        result = speed_up_audio(b"input-mp3", 1.5)

    assert result == b"output-mp3"
    ffmpeg_args = mock_run.call_args.args[0]
    assert ffmpeg_args[0] == "ffmpeg"
    assert "atempo=1.5" in ffmpeg_args


def test_speed_up_audio_noop_when_tempo_is_one():
    assert speed_up_audio(b"input-mp3", 1.0) == b"input-mp3"
