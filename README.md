# EchoScribe

Current release: **v1.2.1**

A lightweight Windows desktop application for local audio transcription and AI meeting summarization using an OpenAI-compatible API.

## Run from source

```bash
pip install -r requirements.txt
python echoscribe/main.py
```

## Run tests

```powershell
$env:PYTHONPATH="echoscribe"
python -m pytest
```

## Local audio library

Every import is copied into an independent record at
`workspace/library/<record_id>/`. PC capture writes there directly. Each record has
exactly one business-data file, `record.json` (schema version 2), containing job
state, normalized and raw transcription data, summary data, translations, errors,
and resumable chunk progress. Binary audio and optional WAV chunks live below its
`audio/` directory.

The History page searches titles, filenames, transcripts, summaries, and all saved
translations. It also filters and sorts records, plays local audio, reloads a record
into the workspace, renames it, retries processing, and opens its directory. Deleted
records first move to `workspace/.trash/`, where they can be restored or explicitly
deleted forever. Trash does not expire automatically.

On startup, old multi-file job directories are migrated in the background. A new
record is atomically written and read back before old JSON, text, or Markdown output
is removed. Records whose source audio has disappeared retain their text and show
Audio unavailable.

## Translation

Transcript and summary translations are manual actions, so opening a record never
incurs API charges. English, Simplified Chinese, and Spanish versions can coexist.
EchoScribe uses the configured OpenAI-compatible provider and summary model. Timed
transcript segments keep timestamps, speakers, and order; long text is processed in
batches. Summary translation preserves its structured fields. Failed or cancelled
translations are not saved, and replacing an existing language requires confirmation.

EchoScribe automatically switches to resumable 10-minute local chunks when audio is
longer than the compatible model's 1500-second request limit. PCM WAV recordings from
PC capture are split natively without FFmpeg. Other long media formats use FFmpeg;
install it on `PATH` when transcribing long MP3, M4A, MP4, WebM, OGG, or FLAC files.
FFmpeg chunks are normalized to 16 kHz mono WAV to remain below common upload limits.
Disabling **Use provider automatic chunking** forces this local strategy for all files.

## Capture PC audio

On Windows, select **Record meeting** to record both the default microphone and
sound playing through the default speakers or headset using WASAPI loopback.
The two sources are aligned and mixed into one 48 kHz mono WAV, even when their
native sample rates differ. Microphone permission must be enabled for desktop apps
in Windows settings. Use headphones to avoid recording speaker sound again through
the microphone; this version does not perform acoustic echo cancellation.
Choose your default input/output devices before recording. A missing microphone
or disconnected device causes an error instead of silently omitting your voice.
Select **Stop recording** to
finalize the WAV in a new library record. EchoScribe
selects the recording automatically but does not upload it until you press
**Transcribe**. This feature requires `PyAudioWPatch`, installed by
`requirements.txt`.

Recording automatically enters the always-on-top compact recorder. After restoring
the main window, select **Shrink to floating recorder** to return to it; minimizing
while recording does the same. It shows a live PCM-level waveform and
elapsed time, can be dragged between screens, restores the main window when clicked,
and includes a dedicated stop control.

## Configuration

Settings are stored at `%APPDATA%/EchoScribe/config.json`.

The interface can switch immediately among English, Simplified Chinese, and
Spanish from Settings. This is independent of the configured summary output
language.

Transcription uses the configured OpenAI-compatible API. The workspace model selector
includes `gpt-4o-transcribe-diarize` and `whisper-large-v3`; custom compatible model
IDs can still be entered in Settings. No local ASR runtime or model download is used.

## Build the Windows executable

Install PyInstaller in the active development environment, then build the checked-in
specification:

```powershell
python -m pip install pyinstaller
pyinstaller --clean --noconfirm echoscribe.spec
```

The windowed executable is written to `dist/EchoScribe.exe`. Before distributing it,
complete [the manual MVP checklist](docs/manual-test-checklist.md), including a run on
a clean Windows user profile.

See `prd.md` for the full product specification.
