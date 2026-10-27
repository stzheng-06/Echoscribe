"""Smoke tests for Phase 1 configuration and models."""
import json
import os
from pathlib import Path

import pytest

from app.config import AppConfig, load_config, save_config
from app.models import AudioMetadata, JobState, MeetingSummary, TranscriptSegment, TranscriptionResult
from app.storage.workspace import atomic_write_json, create_job_directory, ensure_workspace, read_json


def test_default_config_values():
    config = AppConfig()
    assert config.base_url == "https://aihubmix.com/v1"
    assert config.transcription_model == "gpt-4o-transcribe-diarize"
    assert config.summary_model == "gpt-5-mini"
    assert config.summary_language == "zh-CN"
    assert config.summary_length == "medium"
    assert config.ui_language == "en"


def test_load_save_config_roundtrip(tmp_path, monkeypatch):
    app_data = tmp_path / "appdata"
    app_data.mkdir()
    monkeypatch.setenv("APPDATA", str(app_data))

    config = AppConfig(
        api_key="secret",
        base_url="http://localhost/v1",
        summary_model="deepseek-v4-flash",
        summary_language="es",
        summary_length="long",
        ui_language="es",
    )
    save_config(config)

    loaded = load_config()
    assert loaded.api_key == "secret"
    assert loaded.base_url == "http://localhost/v1"
    assert loaded.summary_model == "deepseek-v4-flash"
    assert loaded.summary_language == "es"
    assert loaded.summary_length == "long"
    assert loaded.ui_language == "es"


def test_invalid_summary_defaults_are_normalized(tmp_path, monkeypatch):
    app_data = tmp_path / "appdata"
    config_dir = app_data / "EchoScribe"
    config_dir.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(app_data))
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "summary_model": "legacy-model",
                "summary_language": "unsupported",
                "summary_length": "extra-long",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config()

    assert loaded.summary_model == "gpt-5-mini"
    assert loaded.summary_language == "zh-CN"
    assert loaded.summary_length == "medium"


def test_workspace_creation(tmp_path):
    ensure_workspace(tmp_path)
    job_dir = create_job_directory(tmp_path, "job-123")
    assert job_dir.exists()
    for sub in ("audio", "audio/chunks", "transcript", "transcript/chunks", "summary"):
        assert (job_dir / sub).exists()


def test_atomic_json_write(tmp_path):
    path = tmp_path / "data.json"
    atomic_write_json(path, {"key": "value"})
    assert read_json(path) == {"key": "value"}


def test_models_defaults():
    meta = AudioMetadata(path="/tmp/x.wav", filename="x.wav", extension=".wav", size_bytes=100)
    assert meta.duration_seconds is None

    seg = TranscriptSegment(text="hello")
    assert seg.speaker is None

    result = TranscriptionResult(text="hello", provider="openai", model="whisper-1")
    assert result.segments == []

    summary = MeetingSummary(title="Meeting")
    assert summary.action_items == []

    job = JobState(
        job_id="1",
        mode="quick",
        status="created",
        source_audio="/tmp/x.wav",
        provider="openai",
        model="whisper-1",
        strategy="direct",
        created_at="now",
        updated_at="now",
    )
    assert job.completed_chunk_ids == []
