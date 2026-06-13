# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EchoScribe is a Windows desktop app for recording system audio and microphone input, mixing them into one file, transcribing with the aihubmix Whisper API, and translating the result to Chinese via the aihubmix chat completions API.

## Technology Stack

- Python 3.10+
- PySide6 for the desktop UI
- **PyAudioWPatch** for WASAPI loopback system audio capture
- **sounddevice** for microphone capture
- **numpy** + **scipy** for audio processing and resampling
- **soundfile** for audio file I/O
- `requests` for API calls

No FFmpeg required.

## Common Commands

- Run the app: `python main.py`
- Install dependencies: `pip install -r requirements.txt`

## Project Structure

- `main.py` — application entry point
- `app/main_window.py` — main window UI, state machine, user action handlers, recording timer
- `app/recorder.py` — `AudioRecorder` using PyAudioWPatch for WASAPI loopback + sounddevice for microphone
- `app/audio_tools.py` — audio mixing with scipy resampling
- `app/transcriber.py` — uploads audio to aihubmix transcription API
- `app/translator.py` — translates text via aihubmix chat completions API
- `app/settings.py` — reads/writes config.json
- `app/workers.py` — QThread workers for mixing, transcribing, translating
- `recordings/` — output directory for captured and mixed WAV files

## Configuration

`config.json` stores user settings. Defaults are loaded from `.env`:

- `api_key` — aihubmix API key
- `mic_device_name` — microphone device name or index (optional)
- `system_device_name` — system audio device (optional)
- `output_dir` — audio output directory, defaults to `recordings`
- `translation_model` — chat model for translation
- `whisper_model` — Whisper model for transcription
- `base_url` — aihubmix API base URL

The `.env` file contains local API credentials and must not be committed.

## Recording Pipeline

1. `AudioRecorder.start()` launches two recording threads:
   - System audio: PyAudioWPatch WASAPI loopback (captures system audio like browser)
   - Microphone: sounddevice InputStream
2. `AudioRecorder.stop()` stops threads and saves audio to WAV files.
3. `MixWorker` mixes the two audio files using scipy for proper resampling.
4. `TranscribeWorker` uploads the mixed audio to the aihubmix transcription API.
5. `TranslateWorker` sends the transcription to the aihubmix chat completions API.

## State Machine

`MainWindow` tracks these states: `idle`, `recording`, `stopping`, `mixing`, `transcribing`, `translating`, `done`, `error`. Buttons are enabled/disabled based on the current state.

A recording timer displays elapsed time (MM:SS) while recording.

## Important Notes

- Uses PyAudioWPatch for WASAPI loopback - works without FFmpeg.
- Different sample rates between system audio (48000Hz) and microphone (44100Hz) are handled by scipy resampling.
- All long-running tasks run in QThread workers to keep the UI responsive.
- Translation failures are non-fatal - transcription result is preserved.
- `closeEvent` stops any active recording before the window closes.

Refer to `prd.md` for the full product specification.