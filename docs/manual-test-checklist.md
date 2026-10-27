# EchoScribe MVP Manual Test Checklist

Record the date, Windows version, API provider, and model names for each test run.
Use short disposable media that contains no confidential information unless a test
specifically requires long audio.

## Source and configuration

- [ ] Start with no `%APPDATA%/EchoScribe/config.json`; confirm defaults load.
- [ ] Save an API key, base URL, model names, and workspace; restart and verify them.
- [ ] Switch among English, Simplified Chinese, and Spanish; confirm all window,
      settings, dialog, empty-state, and status text changes without altering output.
- [ ] Confirm the API key is masked and never appears in logs or `record.json`.

## Transcription

- [ ] Import a 10–30 second WAV, confirm metadata, and complete Quick transcription.
- [ ] Repeat with MP3 and one supported video container.
- [ ] Verify unsupported and empty files show clear errors without crashing.
- [ ] Confirm the window stays responsive during upload and cancellation.
- [ ] Confirm every import is copied to a different `library/<record_id>` directory.
- [ ] Confirm the record directory contains only `record.json` as business text data;
      raw response and normalized transcript must be fields inside it.
- [ ] Use invalid credentials, rate limiting, and a network timeout; verify the job
      remains retryable and the detailed error is logged without secrets.

## PC audio capture

- [ ] Play known audio through the default speakers, start PC audio capture, and
      confirm the elapsed timer advances without freezing the interface.
- [ ] Stop recording and confirm a valid WAV is selected but is not automatically
      uploaded to the provider.
- [ ] Start recording and confirm the app automatically hides the main window and
      shows the always-on-top waveform capsule.
- [ ] Restore the main window, click **Shrink to floating recorder**, and confirm the
      compact recorder can be entered again.
- [ ] Repeat by minimizing the main window; confirm it enters the same floating mode.
- [ ] Play loud, quiet, and silent audio and confirm the waveform responds and returns
      smoothly to its baseline without changing the recorded audio.
- [ ] Drag the capsule on one monitor and between monitors; confirm it stays inside
      the usable screen area and remembers its position during the app session.
- [ ] Click the capsule to restore the main window, then repeat and use its Stop button;
      confirm the main window returns and displays the finalizing state.
- [ ] Confirm failures and cancellation while floating restore the main window and do
      not leave an orphaned capsule.
- [ ] Transcribe the captured WAV and verify the expected spoken content.
- [ ] Repeat with wired headphones and Bluetooth output.
- [ ] Change the default output device before recording and confirm the new device is
      captured.
- [ ] Confirm a missing WASAPI loopback device produces a clear recoverable error.
- [ ] Close the window during capture and verify the incomplete `.part` file is
      removed.

## Long audio and resume

- [ ] Transcribe a one-hour meeting with provider automatic chunking enabled.
- [ ] Disable provider chunking and confirm a missing FFmpeg installation gives an
      actionable message.
- [ ] With FFmpeg installed, stop local transcription after several chunks.
- [ ] Restart, import the same source, accept Resume, and verify completed chunks are
      not uploaded again.
- [ ] Confirm merged timestamps are chronological and obvious overlap text is not
      duplicated.

## Summary and output

- [ ] Generate a summary in each configured output language.
- [ ] Confirm decisions and action items do not invent owners or deadlines.
- [ ] Simulate malformed JSON and confirm raw Markdown is retained.
- [ ] Retry a failed summary without retranscribing.
- [ ] Copy the transcript and open the job output folder from the UI.

## History, playback, trash, and migration

- [ ] Restart and confirm completed, failed, cancelled, and interrupted records return.
- [ ] Search title, original filename, transcript, summary, and translated text.
- [ ] Exercise every status/source/language filter and all three sort orders.
- [ ] Play and pause an item, seek, change volume, then load it into the workspace.
- [ ] Rename a record and regenerate its summary; confirm the custom title remains.
- [ ] Move a record to Trash while playing, confirm playback stops, then restore it.
- [ ] Permanently delete one item and clear Trash, accepting both confirmations.
- [ ] Seed one old-format job and restart. Confirm migration is idempotent and that
      missing audio disables playback/retranscription without discarding text.

## Translation

- [ ] Manually translate both transcript and summary into English, Simplified Chinese,
      and Spanish, then restart and confirm all versions remain available.
- [ ] Confirm transcript timestamps, speakers, and segment order do not change.
- [ ] Confirm summary fields, names, numbers, dates, terms, owners, and nulls are kept.
- [ ] Retranslate an existing language and verify confirmation is required.
- [ ] Cancel and simulate failure during a multi-batch translation; confirm no partial
      version replaces the original or a previously saved translation.

## Packaged application

- [ ] Build with `pyinstaller --clean --noconfirm echoscribe.spec`.
- [ ] Launch `dist/EchoScribe.exe` on a clean Windows user profile.
- [ ] Repeat configuration, short transcription, summary, cancellation, and language
      switching checks against the packaged executable.
- [ ] Confirm History playback works in the package (QtMultimedia plugin present).
- [ ] Confirm the packaged app's floating waveform and Stop control work during a
      real WASAPI loopback recording.
