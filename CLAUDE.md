# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EchoScribe is a lightweight Windows desktop application for local audio transcription and AI meeting summarization. It uses an OpenAI-compatible API (default: AiHubMix at `https://aihubmix.com/v1`) through the official OpenAI Python SDK, with a PySide6 UI and local JSON/Markdown persistence.

The codebase is in early implementation. See `prd.md` for the full product specification.

## Technology Stack

- Python 3.11+
- Desktop UI: PySide6
- API client: `openai` Python SDK
- Data models: dataclasses or Pydantic
- Audio metadata: mutagen / soundfile / wave
- Windows system-output capture: PyAudioWPatch WASAPI loopback
- Optional audio conversion/splitting: FFmpeg executable via subprocess
- Background execution: QThreadPool + QRunnable, or one simple QThread worker abstraction
- Testing: pytest
- Packaging: PyInstaller (only after source runs reliably)

## Common Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python echoscribe/main.py
```

Run all tests:

```bash
pytest
```

Run a single test:

```bash
pytest tests/test_normalization.py
```

## Project Structure

```text
echoscribe/
├── main.py
├── requirements.txt
├── README.md
├── app/
│   ├── config.py          # Config load/save (%APPDATA%/EchoScribe/config.json)
│   ├── models.py          # AudioMetadata, TranscriptSegment, TranscriptionResult, MeetingSummary, JobState
│   ├── exceptions.py      # Application-level exceptions
│   ├── ui/
│   │   ├── main_window.py
│   │   └── settings_dialog.py
│   ├── services/
│   │   ├── transcription_service.py
│   │   ├── summarization_service.py
│   │   ├── job_service.py
│   │   └── export_service.py
│   ├── providers/
│   │   ├── asr_base.py
│   │   ├── openai_compatible_asr.py
│   │   ├── llm_base.py
│   │   └── openai_compatible_llm.py
│   ├── audio/
│   │   ├── probe.py
│   │   ├── splitter.py
│   │   └── converter.py
│   ├── storage/
│   │   ├── workspace.py
│   │   └── atomic_json.py
│   └── workers/
│       └── task_runner.py
├── tests/
└── workspace/             # Default: %APPDATA%/EchoScribe/workspace
```

Keep files small and focused. Do not create empty modules.

## Architecture Rules

- UI code must not call the OpenAI SDK directly.
- Business services depend on interfaces (`ASRProvider`, `LLMProvider`), not concrete providers.
- Provider-specific responses must be normalized before reaching the UI.
- Storage must not depend on PySide6.
- Summarization must not depend on a specific ASR provider.
- Long-audio orchestration must be separate from audio splitting.
- Do not add local ASR runtimes, model managers, PyTorch, or model weights.
- Every long-running operation must run outside the UI thread.
- System-audio capture must stream directly to disk outside the UI thread and finalize
  a WAV before it enters the normal transcription workflow.
- Files must be written atomically when practical (use atomic replace for critical JSON state files).

## Default Configuration

Stored at `%APPDATA%/EchoScribe/config.json`:

```json
{
  "api_key": "",
  "base_url": "https://aihubmix.com/v1",
  "transcription_model": "gpt-4o-transcribe-diarize",
  "summary_model": "gpt-4o-mini",
  "summary_language": "zh-CN",
  "ui_language": "en",
  "default_mode": "auto",
  "workspace_dir": "%APPDATA%/EchoScribe/workspace",
  "copy_source_audio": false,
  "enable_provider_auto_chunking": true,
  "local_chunk_minutes": 15,
  "local_chunk_overlap_seconds": 2
}
```

Do not hardcode AiHubMix-specific logic outside the OpenAI-compatible provider.

## Provider Interface

```python
class ASRProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path, *, model: str, diarize: bool, language: str | None = None) -> TranscriptionResult: ...
    @abstractmethod
    def supports_long_audio(self) -> bool: ...
    @abstractmethod
    def supports_diarization(self) -> bool: ...
```

`OpenAICompatibleASRProvider` is the only MVP implementation. It initializes `openai.OpenAI` with configurable `api_key` and `base_url`, calls `client.audio.transcriptions.create()`, and converts SDK responses into `TranscriptionResult`. Do not expose SDK objects outside this provider.

## Transcription Strategy

- If the provider supports the file and long-audio upload, upload the original file directly (preferred; uses `chunking_strategy="auto"`).
- Else if conversion is required, convert via FFmpeg.
- If the provider cannot process the full file, split locally and process chunks sequentially (default 15 minutes, 2-second overlap).

Resume behavior: skip already completed chunks; merge segments in chronological order; add chunk start offset to timestamps; remove obvious overlap duplicates with conservative text matching.

## Meeting Summarization

- Runs after a successful transcription.
- Receives normalized transcript text and optional structured segments, never an ASR SDK response object.
- Expected output sections: Title, Overview, Key Discussion Points, Decisions, Action Items, Open Questions, Next Meeting.
- If JSON parsing fails, save raw text as Markdown instead of failing the job.
- For very long transcripts, use hierarchical summarization only when length exceeds the configured context threshold.

## Security and Secrets

- Never print the complete API key.
- Never include the API key in exported job files.
- Mask the API key in the UI.
- Do not commit `.env`, `config.json`, or workspace data.
- Storing the API key in local configuration is acceptable for the MVP; mark OS credential storage as a future improvement.

## Error Handling

Application-level exceptions to implement:

```text
ConfigurationError
AudioValidationError
AudioConversionError
ProviderAuthenticationError
ProviderRateLimitError
ProviderTimeoutError
ProviderResponseError
JobStateError
SummaryParseError
```

Expected provider and file errors must not crash the application.

## Implementation Phases

Implement in order from `prd.md`:

1. Skeleton (models, config, workspace, minimal UI)
2. Cloud transcription (ASR provider, normalization, direct upload)
3. Background jobs (task runner, QThread, progress, cancellation, persistence)
4. Meeting summary (LLM provider, structured summary, retry)
5. Long-audio fallback (FFmpeg detection, splitting, resume, merge)
6. Tests and packaging

## Coding Rules from PRD

- Implement one phase at a time.
- Before editing, inspect existing files and reuse working code.
- Do not rewrite unrelated modules.
- Keep public interfaces stable after they are used.
- Do not add features outside the PRD.
- Do not add a dependency without explaining why it is required.
- Prefer standard library solutions when they remain clear.
- Add type hints to public functions and methods.
- Use `pathlib.Path` for file paths.
- Use `logging`, not `print`, for diagnostics.
- Keep provider SDK objects inside provider modules.
- Keep UI logic thin.
- Keep every user-facing GUI string in `app/i18n.py`; English, Simplified Chinese,
  and Spanish catalogs must contain identical keys.
- Preserve the warm-neutral Notion-inspired QSS system in `app/ui/theme.py` and
  retain visible focus, hover, disabled, loading, and empty states.
- Do not store secrets in source code.
- Do not silently catch exceptions.
- Write tests for normalization and resumable job behavior.
- After each phase, run the application and relevant tests.
- Update README instructions when behavior changes.
- Leave explicit TODO comments only for approved post-MVP work.
