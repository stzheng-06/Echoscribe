"""Configuration loading and saving for EchoScribe."""
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

SUMMARY_MODELS = ("gpt-5-mini", "deepseek-v4-flash", "gpt-5.4-low")
SUMMARY_LENGTHS = ("short", "medium", "long")
SUMMARY_LANGUAGES = ("zh-CN", "en", "es")

DEFAULT_CONFIG: dict[str, object] = {
    "api_key": "",
    "base_url": "https://aihubmix.com/v1",
    "transcription_model": "gpt-4o-transcribe-diarize",
    "summary_model": "gpt-5-mini",
    "summary_language": "zh-CN",
    "summary_length": "medium",
    "ui_language": "en",
    "default_mode": "auto",
    "workspace_dir": os.path.join(os.environ.get("APPDATA", ""), "EchoScribe", "workspace"),
    "copy_source_audio": True,
    "enable_provider_auto_chunking": True,
    "local_chunk_minutes": 10,
    "local_chunk_overlap_seconds": 2,
    "transcription_language": "auto",
}


@dataclass
class AppConfig:
    api_key: str = ""
    base_url: str = "https://aihubmix.com/v1"
    transcription_model: str = "gpt-4o-transcribe-diarize"
    summary_model: str = "gpt-5-mini"
    summary_language: str = "zh-CN"
    summary_length: str = "medium"
    ui_language: str = "en"
    default_mode: str = "auto"
    workspace_dir: str = field(default_factory=lambda: DEFAULT_CONFIG["workspace_dir"])
    copy_source_audio: bool = True
    enable_provider_auto_chunking: bool = True
    local_chunk_minutes: int = 10
    local_chunk_overlap_seconds: int = 2
    transcription_language: str = "auto"


def config_path() -> Path:
    app_data = os.environ.get("APPDATA", "")
    if not app_data:
        raise ConfigurationError("APPDATA environment variable is not set")
    return Path(app_data) / "EchoScribe" / "config.json"


def _expand_path(value: str) -> str:
    """Expand %APPDATA% and other Windows env vars in config strings."""
    if os.name == "nt":
        for key, val in sorted(os.environ.items(), key=lambda kv: -len(kv[0])):
            value = value.replace(f"%{key}%", val)
    return os.path.expandvars(value)


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        logger.info("Config not found at %s; using defaults", path)
        return AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in config file {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Cannot read config file {path}: {exc}") from exc

    merged = {**DEFAULT_CONFIG, **data}
    merged["workspace_dir"] = _expand_path(str(merged.get("workspace_dir", DEFAULT_CONFIG["workspace_dir"])))

    try:
        transcription_language = str(merged.get("transcription_language", "auto"))
        if transcription_language not in {"auto", "zh", "es"}:
            transcription_language = "auto"
        summary_model = str(merged.get("summary_model", DEFAULT_CONFIG["summary_model"]))
        if summary_model not in SUMMARY_MODELS:
            summary_model = str(DEFAULT_CONFIG["summary_model"])
        summary_language = str(
            merged.get("summary_language", DEFAULT_CONFIG["summary_language"])
        )
        if summary_language not in SUMMARY_LANGUAGES:
            summary_language = str(DEFAULT_CONFIG["summary_language"])
        summary_length = str(
            merged.get("summary_length", DEFAULT_CONFIG["summary_length"])
        )
        if summary_length not in SUMMARY_LENGTHS:
            summary_length = str(DEFAULT_CONFIG["summary_length"])
        return AppConfig(
            api_key=str(merged.get("api_key", "")),
            base_url=str(merged.get("base_url", DEFAULT_CONFIG["base_url"])),
            transcription_model=str(merged.get("transcription_model", DEFAULT_CONFIG["transcription_model"])),
            summary_model=summary_model,
            summary_language=summary_language,
            summary_length=summary_length,
            ui_language=str(merged.get("ui_language", DEFAULT_CONFIG["ui_language"])),
            default_mode=str(merged.get("default_mode", DEFAULT_CONFIG["default_mode"])),
            workspace_dir=str(merged["workspace_dir"]),
            # Schema-v2 library records always retain their own audio copy.
            copy_source_audio=True,
            enable_provider_auto_chunking=bool(merged.get("enable_provider_auto_chunking", True)),
            local_chunk_minutes=int(merged.get("local_chunk_minutes", 10)),
            local_chunk_overlap_seconds=int(merged.get("local_chunk_overlap_seconds", 2)),
            transcription_language=transcription_language,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid config value: {exc}") from exc


def save_config(config: AppConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "api_key": config.api_key,
        "base_url": config.base_url,
        "transcription_model": config.transcription_model,
        "summary_model": config.summary_model,
        "summary_language": config.summary_language,
        "summary_length": config.summary_length,
        "ui_language": config.ui_language,
        "default_mode": config.default_mode,
        "workspace_dir": config.workspace_dir,
        "copy_source_audio": config.copy_source_audio,
        "enable_provider_auto_chunking": config.enable_provider_auto_chunking,
        "local_chunk_minutes": config.local_chunk_minutes,
        "local_chunk_overlap_seconds": config.local_chunk_overlap_seconds,
        "transcription_language": config.transcription_language,
    }
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise ConfigurationError(f"Cannot write config file {path}: {exc}") from exc


def mask_api_key(key: str) -> str:
    """Return a masked representation of an API key for UI/logs."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "..." + key[-4:]
