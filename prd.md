# EchoScribe MVP PRD

## 1. Product Summary

EchoScribe is a lightweight Windows desktop application for local audio transcription and AI meeting summarization.

The application must support three primary use cases:

1. **Quick transcription** for short audio files, including clips that are only a few seconds long.
2. **Meeting transcription** for long audio files, including meetings longer than one hour.
3. **PC audio capture** for recording sound playing through the default Windows
   output device before transcription.

The main workflow is **importing an existing audio file**. Windows system-audio
capture is also part of the MVP; microphone recording remains outside the core MVP.

Transcription uses an OpenAI-compatible API through the official OpenAI Python SDK.
The application does not bundle or manage local ASR runtimes or model weights.

---

## 2. MVP Goals

The MVP must allow a user to:

1. Start the desktop application.
2. Configure an API key, base URL, transcription model, and summary model.
3. Import a local audio file.
4. Read the detected file duration and metadata.
5. Select Quick Mode or Meeting Mode.
6. Transcribe the audio without freezing the UI.
7. Save the normalized transcript and raw provider response.
8. Generate a structured meeting summary when requested.
9. Resume an interrupted long-audio job when local chunking is used.
10. Open the output folder directly from the application.
11. Capture audio playing through the default Windows output device and select the
    resulting WAV recording for transcription.

---

## 3. Non-Goals

Do not implement the following in the MVP:

- User accounts or login
- Cloud storage or synchronization
- Team collaboration
- CRM integration
- Online meeting bots
- Real-time streaming transcription
- Real-time subtitles
- Automatic meeting joining
- Mobile applications
- macOS or Linux support
- A database server
- Complex history management
- Audio waveform visualization
- Rich-text editing
- PDF or DOCX export
- Bundled local ASR models
- Implicit model downloading or downloading merely by selecting a provider
- Automatic updates
- Plugin marketplace

Use local JSON files instead of a database.

---

## 4. Supported Workflows

### 4.1 Quick Transcription

Designed for audio from a few seconds to several minutes.

Default workflow:

```text
Import audio
-> Validate file
-> Send audio to ASR provider
-> Normalize result
-> Display transcript
-> Save transcript files
```

Quick Mode behavior:

- Summary generation is optional.
- Speaker diarization is not required.
- Local chunking should not be used unless required by provider limits.
- The transcript should be easy to copy.
- The UI should minimize unnecessary steps.

### 4.2 Meeting Transcription

Designed for long-form audio, including files longer than one hour.

Default workflow:

```text
Import audio
-> Probe metadata
-> Create persistent job
-> Select transcription strategy
-> Transcribe
-> Normalize segments and speakers
-> Save transcript
-> Generate meeting summary
-> Save final output
```

Meeting Mode behavior:

- Prefer a diarization-capable model.
- Preserve speaker labels and timestamps when available.
- Save intermediate job state.
- Support resumable local chunk processing.
- Generate a structured meeting summary on demand.

### 4.3 Windows System-Audio Capture

Designed for recording audio currently playing through the PC speakers or headset.

```text
Start PC audio capture
-> Record the default Windows output through WASAPI loopback
-> Stop and finalize a local WAV file
-> Select the recording automatically
-> Transcribe through the existing Quick or Meeting workflow
```

Requirements:

- Capture the default Windows output device through WASAPI loopback.
- Run capture outside the UI thread and show elapsed recording time.
- Stream frames directly to disk rather than holding the recording in memory.
- Finalize a valid PCM WAV before enabling transcription.
- Store captures under the configured workspace `recordings/` directory.
- Show a clear error if WASAPI or a loopback device is unavailable.
- Do not send a recording to the API automatically; require Transcribe confirmation.

---

## 5. Default API Integration

Use the official OpenAI Python SDK.

```python
import openai

client = openai.OpenAI(
    api_key="<AIHUBMIX_API_KEY>",
    base_url="https://aihubmix.com/v1",
)

with open("sample-speech-1m.wav", "rb") as audio_file:
    response = client.audio.transcriptions.create(
        model="gpt-4o-transcribe-diarize",
        file=audio_file,
        chunking_strategy="auto",
    )

print(response.text)
```

Default settings:

```json
{
  "base_url": "https://aihubmix.com/v1",
  "transcription_model": "gpt-4o-transcribe-diarize",
  "summary_model": "gpt-4o-mini",
  "summary_language": "zh-CN"
}
```

The API key, base URL, and model names must be configurable.

Do not hardcode AiHubMix-specific logic outside the OpenAI-compatible provider.

---

## 6. Architecture Principles

The codebase must follow these rules:

1. UI code must not call the OpenAI SDK directly.
2. Business services must depend on interfaces, not concrete providers.
3. Provider-specific responses must be normalized before reaching the UI.
4. Storage must not depend on PySide6.
5. Summarization must not depend on a specific ASR provider.
6. Long-audio orchestration must be separate from audio splitting.
7. Local ASR must be addable as an optional provider.
8. Optional heavy dependencies must not be installed by default.
9. Every long-running operation must run outside the UI thread.
10. Files must be written atomically when practical.

Use straightforward Python. Avoid unnecessary design patterns, dependency injection frameworks, event buses, and excessive abstraction.

---

## 7. Recommended Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| Desktop UI | PySide6 |
| API client | openai Python SDK |
| Audio metadata | soundfile, mutagen, or wave where applicable |
| Optional audio conversion/splitting | ffmpeg executable through subprocess |
| Data models | dataclasses or Pydantic |
| Local persistence | JSON and Markdown files |
| Background execution | QThreadPool + QRunnable, or one simple QThread worker abstraction |
| Windows system capture | PyAudioWPatch WASAPI loopback |
| Testing | pytest |
| Packaging | PyInstaller, after MVP works from source |

FFmpeg must be optional in the first implementation. Files already accepted by the selected ASR provider should be uploaded directly. FFmpeg is required only for conversion or local chunking.

---

## 8. Project Structure

```text
echoscribe/
├── main.py
├── requirements.txt
├── README.md
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── exceptions.py
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
│   ├── test_normalization.py
│   ├── test_job_resume.py
│   ├── test_workspace.py
│   └── fixtures/
└── workspace/
```

Keep files small and focused. Do not create empty modules that are not used.

---

## 9. Core Data Models

Use typed models for all boundaries.

### 9.1 AudioMetadata

```python
@dataclass
class AudioMetadata:
    path: str
    filename: str
    extension: str
    size_bytes: int
    duration_seconds: float | None
    sample_rate: int | None
    channels: int | None
```

### 9.2 TranscriptSegment

```python
@dataclass
class TranscriptSegment:
    start: float | None
    end: float | None
    speaker: str | None
    text: str
```

### 9.3 TranscriptionResult

```python
@dataclass
class TranscriptionResult:
    text: str
    language: str | None
    duration_seconds: float | None
    segments: list[TranscriptSegment]
    provider: str
    model: str
    raw_response: dict
```

### 9.4 MeetingSummary

```python
@dataclass
class MeetingSummary:
    title: str
    overview: str
    key_points: list[str]
    decisions: list[str]
    action_items: list[dict]
    open_questions: list[str]
    next_meeting: str | None
    markdown: str
```

Each action item should use this shape:

```json
{
  "task": "Prepare the revised quotation",
  "owner": "Speaker 2",
  "deadline": "2026-08-07",
  "status": "open"
}
```

Unknown values must be `null` or an empty list. Do not invent owners or deadlines.

### 9.5 JobState

```python
@dataclass
class JobState:
    job_id: str
    mode: str
    status: str
    source_audio: str
    provider: str
    model: str
    strategy: str
    created_at: str
    updated_at: str
    completed_chunk_ids: list[int]
    failed_chunk_id: int | None
    error_message: str | None
```

Allowed statuses:

```text
created
probing
ready
transcribing
summarizing
completed
failed
cancelled
```

---

## 10. Provider Interfaces

### 10.1 ASRProvider

```python
from abc import ABC, abstractmethod
from pathlib import Path

class ASRProvider(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool,
        language: str | None = None,
    ) -> TranscriptionResult:
        raise NotImplementedError

    @abstractmethod
    def supports_long_audio(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports_diarization(self) -> bool:
        raise NotImplementedError
```

### 10.2 OpenAICompatibleASRProvider

Responsibilities:

- Initialize `openai.OpenAI` with configurable `api_key` and `base_url`.
- Open audio files in binary mode.
- Call `client.audio.transcriptions.create()`.
- Use `chunking_strategy="auto"` when supported and enabled.
- Convert SDK responses into `TranscriptionResult`.
- Preserve the complete serializable raw response.
- Convert API exceptions into application exceptions.

Do not expose SDK objects outside this provider.

## 11. Transcription Strategy

The transcription service decides how to process a file.

```text
If provider supports the file and its duration is within the known request limit:
    upload the original file directly
Else if conversion is required:
    convert to a supported format
If provider cannot process the full file:
    split locally and process chunks sequentially
```

### 11.1 Direct Upload Strategy

Use this by default for the AiHubMix diarization model up to its 1500-second request
limit. Provider-side automatic chunking does not override a model duration rejection.

Advantages:

- Minimum local processing
- Lower application complexity
- Provider-managed chunking
- Better diarization continuity

### 11.2 Local Chunk Strategy

Use only when required.

Requirements:

- Default and maximum cloud chunk duration: 10 minutes.
- Configurable chunk duration from 1 to 10 minutes.
- Optional overlap: 2 seconds.
- Store each chunk in the job workspace.
- Save each chunk result immediately.
- Skip already completed chunks on resume.
- Merge segments in chronological order.
- Add the chunk start offset to segment timestamps.
- Remove obvious overlap duplicates using conservative text matching.
- Never delete chunk results until the final transcript is saved.
- Force local chunks when known audio duration exceeds the provider/model limit.
- Split uncompressed PCM WAV streams natively; require FFmpeg only for media formats
  that cannot be safely split with Python's WAV reader.

Do not implement semantic or silence-based splitting in the MVP.

---

## 12. Audio Import and Validation

The user imports one local audio or video file.

Initial accepted extensions:

```text
.wav
.mp3
.m4a
.mp4
.webm
.ogg
.flac
```

Validation rules:

- File must exist.
- File must be readable.
- File size must be greater than zero.
- Unsupported extensions must show a clear error.
- If metadata probing fails, the user may still attempt direct upload.
- Never load the entire audio file into memory.

Mode recommendation:

```text
duration <= 10 minutes -> recommend Quick Mode
duration > 10 minutes -> recommend Meeting Mode
unknown duration -> ask the user to select a mode
```

The user can override the recommendation.

---

## 13. Meeting Summarization

Summarization is optional and runs after a successful transcription.

The summarizer receives normalized transcript text and optional structured segments. It must not receive an ASR SDK response object.

The summary prompt must instruct the model to:

- Use only information present in the transcript.
- Preserve names, numbers, dates, and technical terms.
- Identify decisions separately from discussion.
- Extract action items with owner and deadline only when explicit.
- Mark uncertain owners or deadlines as unknown.
- Avoid inventing commitments.
- Produce the selected output language.
- Return structured JSON when possible.

Expected sections:

```text
Title
Overview
Key Discussion Points
Decisions
Action Items
Open Questions
Next Meeting
```

The service must validate the returned structure. If JSON parsing fails, save the raw text as Markdown instead of failing the full job.

For very long transcripts, the summarization service may use hierarchical summarization:

```text
split transcript text
-> summarize each section
-> combine section summaries
-> create final structured summary
```

Implement this only when transcript length exceeds the configured context threshold.

---

## 14. Workspace and File Output

Default workspace:

```text
%APPDATA%/EchoScribe/workspace/
```

Each imported file creates one job directory:

```text
workspace/
└── <job_id>/
    ├── source.json
    ├── job.json
    ├── audio/
    │   ├── original.<ext>
    │   ├── converted.wav
    │   └── chunks/
    │       ├── chunk_000.wav
    │       └── chunk_001.wav
    ├── transcript/
    │   ├── raw_response.json
    │   ├── transcript.json
    │   ├── transcript.txt
    │   └── chunks/
    │       ├── chunk_000.json
    │       └── chunk_001.json
    └── summary/
        ├── summary.json
        └── summary.md
```

Rules:

- Copy the imported file into the workspace only when the user enables that option.
- Otherwise store the absolute source path in `source.json`.
- Save normalized output separately from raw provider output.
- Write job progress after every completed stage.
- Use UTF-8 for all text and JSON files.
- Use atomic replace for critical JSON state files.

---

## 15. Configuration

Store configuration at:

```text
%APPDATA%/EchoScribe/config.json
```

Example:

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
  "local_chunk_minutes": 10,
  "local_chunk_overlap_seconds": 2
}
```

Security requirements:

- Never print the complete API key.
- Never include the API key in exported job files.
- Mask the API key in the UI.
- Do not commit `.env`, `config.json`, or workspace data.

For the MVP, storing the API key in local configuration is acceptable. Add a code comment marking OS credential storage as a future improvement.

---

## 16. User Interface

Use one main window and one settings dialog.

### 16.1 Main Window

Required controls:

- Import Audio button
- Selected file display
- File duration display
- Mode selector: Auto, Quick, Meeting
- Transcribe button
- Generate Summary button
- Cancel button
- Progress indicator
- Status text
- Transcript text area
- Summary text area
- Copy Transcript button
- Open Output Folder button
- Capture PC Audio / Stop Recording button

Behavior:

- Disable Transcribe until a valid file is selected.
- Disable Generate Summary until transcription succeeds.
- Keep the UI responsive during all operations.
- Show concise errors in the UI.
- Save detailed errors to a local log file.
- Do not block the main thread with file uploads, conversion, splitting, or summarization.
- Do not block the main thread while recording system audio.

### 16.2 Settings Dialog

Required fields:

- API key
- Base URL
- Transcription model
- Summary model
- Summary language
- Workspace directory
- Local chunk duration
- Copy source audio toggle
- Interface language: English, Simplified Chinese, or Spanish

Include a Test Connection button only if it can use a low-cost request. Otherwise omit it from the MVP.

### 16.3 Visual Design and Localization

- Use a Notion-inspired visual language: warm neutral surfaces, restrained borders,
  generous whitespace, clear editorial hierarchy, and compact controls.
- Preserve a focused desktop-workspace feel; avoid gradients, heavy shadows,
  excessive card nesting, and decorative elements that compete with the transcript.
- Provide complete GUI translations for English, Simplified Chinese, and Spanish.
- Persist the selected interface language in application configuration and apply it
  immediately after Settings is saved. Transcript and summary output languages remain
  independent from the interface language.
- Localize buttons, labels, empty states, progress/status text, dialogs, validation
  messages, file-picker titles, and settings fields.
- Use fonts with suitable Windows fallbacks for Latin and Chinese text, and retain
  visible keyboard focus states with readable contrast.
- Size non-wrapping navigation, selectors, and settings controls from the active
  translation. Long Spanish labels must remain visible without reducing Chinese or
  English readability; use multi-row action/filter layouts where horizontal space is
  constrained.
- Use a bundled, original SVG icon set with consistent stroke weight for navigation
  and actions. The minimalist EchoScribe mark combines a document with an audio
  waveform and must remain legible at Windows title-bar and sidebar sizes.
- Bundle every SVG asset in both source runs and PyInstaller builds; never depend on
  network-hosted interface assets.

---

## 17. Error Handling

Create application-level exceptions:

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

Required behavior:

| Error | User-facing behavior |
|---|---|
| Missing API key | Block API task and open settings |
| Invalid file | Show validation message |
| Authentication failure | Report invalid or expired API key |
| Rate limit | Keep job resumable and show retry message |
| Timeout | Keep existing intermediate results |
| Chunk failure | Record failed chunk and allow resume |
| Summary failure | Preserve transcript and allow summary retry |
| JSON write failure | Show storage error and do not report completion |

Do not crash the application for expected provider or file errors.

---

## 18. Logging

Write logs to:

```text
%APPDATA%/EchoScribe/logs/echoscribe.log
```

Log:

- Job ID
- Stage transitions
- Provider name
- Model name
- File metadata
- Chunk IDs
- Error type and traceback

Do not log:

- Complete API keys
- Full audio content
- Full transcript text by default

---

## 19. Minimal Dependencies

`requirements.txt` should contain only dependencies needed for cloud transcription and the desktop UI.

Example:

```text
PySide6
openai
pydantic
mutagen
```

Add audio or parsing packages only when actually required.

Do not add PyTorch, CUDA packages, local ASR engines, or model weights to the
application installation.

---

## 20. Implementation Order for Codex

Codex should implement the project in this order.

### Phase 1: Skeleton

- Create project structure.
- Add typed models and exceptions.
- Add config loading and saving.
- Add workspace creation.
- Add a minimal PySide6 main window.

### Phase 2: Cloud Transcription

- Implement `ASRProvider`.
- Implement `OpenAICompatibleASRProvider`.
- Normalize text-only and segmented responses.
- Add audio import and direct upload.
- Save raw and normalized transcript output.

### Phase 3: Background Jobs

- Add reusable task runner.
- Move transcription out of the UI thread.
- Add progress and cancellation state.
- Persist job status.

### Phase 4: Meeting Summary

- Implement LLM provider abstraction.
- Implement OpenAI-compatible summary provider.
- Generate and save structured summary.
- Add summary retry without retranscribing.

### Phase 5: Long-Audio Fallback

- Add optional FFmpeg detection.
- Add local time-based splitting.
- Save chunk results incrementally.
- Implement resume and merge.

### Phase 6: Tests and Packaging

- Add unit tests for normalization, state persistence, resume, and exports.
- Add a manual test checklist.
- Add PyInstaller configuration only after source execution is stable.

Do not implement later phases before the current phase works.

---

## 21. Codex Coding Rules

These rules are intended to keep vibe coding controlled and reviewable.

1. Implement one phase at a time.
2. Before editing, inspect existing files and reuse working code.
3. Do not rewrite unrelated modules.
4. Keep public interfaces stable after they are used.
5. Do not add features outside this PRD.
6. Do not add a dependency without explaining why it is required.
7. Prefer standard library solutions when they remain clear.
8. Add type hints to public functions and methods.
9. Use `pathlib.Path` for file paths.
10. Use `logging`, not `print`, for diagnostics.
11. Keep provider SDK objects inside provider modules.
12. Keep UI logic thin.
13. Do not store secrets in source code.
14. Do not silently catch exceptions.
15. Write tests for normalization and resumable job behavior.
16. After each phase, run the application and relevant tests.
17. Update README instructions when behavior changes.
18. Leave explicit TODO comments only for approved post-MVP work.

---

## 22. Acceptance Criteria

The MVP is complete when all criteria below pass.

### Short Audio

- A user can import a 10-30 second audio file.
- The application transcribes it through the configured OpenAI-compatible API.
- The transcript appears in the UI.
- `transcript.txt`, `transcript.json`, and `raw_response.json` are saved.

### Long Meeting

- A user can import an audio file longer than one hour.
- The application remains responsive.
- The job state is saved before transcription begins.
- Direct provider-side automatic chunking is used only within the known request limit;
  longer input automatically uses resumable local chunks.
- If local chunk mode is selected, completed chunks are not repeated after restart.
- Speaker labels and timestamps are preserved when returned by the provider.

### System Audio

- A user can start and stop capture of the default Windows output device.
- The UI stays responsive and shows elapsed recording time.
- Stopping creates a readable WAV and selects it for transcription.
- Captured audio uses the same transcription, persistence, cancellation, and summary
  workflows as imported audio.

### Summary

- A completed transcript can be summarized without retranscription.
- The output includes overview, key points, decisions, action items, open questions, and next meeting.
- Missing owners and deadlines are not invented.
- `summary.md` and `summary.json` are saved.

### Architecture

- The UI does not import or instantiate the OpenAI SDK directly.
- Replacing the ASR provider does not require changes to UI code.
- Heavy local ASR packages are not default dependencies.
- Job state and output use local files, not a database.
- Switching among English, Simplified Chinese, and Spanish updates all GUI chrome
  without changing transcript or summary content.

### Stability

- API errors do not crash the application.
- Closing or restarting after a chunk failure preserves completed chunk results.
- Secrets are not written to logs or job output.

---

## 23. Manual Test Checklist

1. Start with no configuration file.
2. Save API settings and restart the application.
3. Import a 15-second WAV file and transcribe it.
4. Import an MP3 file and transcribe it.
5. Import a file with an unsupported extension.
6. Test an invalid API key.
7. Test a temporary network failure.
8. Generate a summary from a completed transcript.
9. Retry summary generation after a simulated failure.
10. Run local chunk mode on a long test file.
11. Stop after several chunks, restart, and resume.
12. Verify no API key appears in logs or job files.
13. Verify the UI remains responsive during API calls.

---

## 24. Future Extensions

The architecture should permit, but the MVP must not implement:

- Microphone recording
- SRT and VTT export
- Searchable transcript history
- Speaker renaming
- Batch file processing
- Translation
- Custom summary templates
- Local LLM summarization
- macOS and Linux support
# Local Library and Translation Addendum (Schema Version 2)

EchoScribe stores each imported or captured audio item below
`workspace/library/<record_id>`. Imported media is always copied; duplicate imports
create independent records. PC capture writes directly to the record. The only
business-data file in a record directory is atomically replaced `record.json`, which
contains source metadata, job/error/chunk state, normalized and raw transcription,
structured and rendered summary, and retained `en`, `zh-CN`, and `es` translations.

History provides full-text search, status/source/language filters, newest/oldest/title
sorting, QtMultimedia playback, load, rename, retranscription, summary regeneration,
folder access, and deletion. Deletion moves records to `workspace/.trash`; restoration,
individual permanent deletion, and confirmed clearing are supported without automatic
expiry. Missing source audio retains all textual data but disables audio-dependent actions.

Legacy multi-output jobs are migrated at startup. Migration copies external media,
moves application-generated recordings after verification, writes and reads back the
new record, and only then removes old JSON/TXT/Markdown. A migration marker makes the
operation idempotent and restart-safe.

Translation is never automatic. It reuses the configured OpenAI-compatible LLM and
summary model. Transcript batching follows segment boundaries at approximately 12,000
characters and preserves timestamps, speakers, and order. Summary translation retains
the complete structure and explicit names, values, terms, owners, and nulls. A version
is saved only after every batch succeeds; cancellation or failure leaves prior content
untouched, while replacement of an existing target language requires confirmation.

During PC audio capture, recording automatically enters a frameless, always-on-top
floating controller. It can also be re-entered explicitly or by minimizing the main window. The compact
controller displays a live, non-persisted PCM RMS waveform, a shared elapsed timer,
and a dedicated Stop action. It is draggable within the active screen bounds and
restores the main window on click, completion, cancellation, or failure.
