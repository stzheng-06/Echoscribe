# Repository Guidelines

## Project Structure & Module Organization

EchoScribe is a Python 3.11+ Windows desktop application. The entry point is `echoscribe/main.py`. Application code lives under `echoscribe/app/`: configuration and shared models are at the package root, persistence belongs in `storage/`, and PySide6 views belong in `ui/`. Tests live in `tests/`; name new files `test_<feature>.py`. Product requirements and architecture constraints are documented in `prd.md` and `CLAUDE.md`. Keep generated workspace data and local configuration outside the repository.

## Build, Test, and Development Commands

Create and activate a virtual environment before installing dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python echoscribe/main.py
$env:PYTHONPATH="echoscribe"; python -m pytest -q
```

The first three commands prepare the environment and launch the application. The final command runs the full suite with the package import path required by the current layout. Run one file with `python -m pytest tests/test_phase1.py -q`. Optional local-ASR dependencies belong in `requirements-local-asr.txt` and should only be installed when working on that provider.

## Coding Style & Naming Conventions

Use four-space indentation, UTF-8, type hints on public functions, and `pathlib.Path` for paths. Follow standard Python naming: `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_CASE` for constants. Keep modules focused, UI logic thin, and provider SDK objects inside provider modules. Use `logging` instead of `print`; never silently swallow exceptions. No formatter or linter is currently configured, so keep changes PEP 8-compatible and avoid unrelated reformatting.

## Testing Guidelines

Tests use pytest and plain `assert` statements. Add focused unit tests for configuration, model defaults, provider-response normalization, atomic persistence, and resumable jobs. Use pytest fixtures such as `tmp_path` and `monkeypatch` to isolate filesystem and environment changes. Every bug fix should include a regression test, and the full suite should pass before review.

## Commit & Pull Request Guidelines

This checkout contains no Git history from which to infer an established convention. Use short, imperative subjects such as `Add transcript normalization tests`, and keep each commit scoped to one concern. Pull requests should explain the user-visible change, list verification commands, link the relevant issue or PRD section, and include screenshots for UI changes. Call out dependency, configuration, or data-format changes explicitly.

## Security & Configuration

Never commit `.env`, API keys, `%APPDATA%/EchoScribe/config.json`, or workspace exports. Mask secrets in UI and logs, and preserve atomic writes for critical JSON state.
