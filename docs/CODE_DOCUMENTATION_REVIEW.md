# Code Documentation Review

This note summarizes the documentation pass applied to the repository.

## What was documented

- Module docstrings were added to Python files under `src/`, `app/`, `scripts/` and `tests/`.
- Function and class docstrings were added when missing.
- Inline comments were added to the most important flows:
  - live X/Twitter search and preview
  - query anchor filtering
  - multilingual FinBERT translation
  - live scheduled ingestion
  - medallion Bronze/Silver/Gold writes
  - Streamlit upload and processing entry points

## What was intentionally not removed

The patch does not remove source files, scripts, tests, SQL, infrastructure templates,
or documentation files. Those files are part of the project history or deployment flow.
Only obvious temporary files are removed automatically: `.bak`, `.bak_*`, `.DS_Store`,
Python bytecode caches and rejected patch fragments.

## Recommended validation after applying

```bash
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

## Git safety check

Before committing, verify that no secrets or local environment files are staged:

```bash
git status --short | grep -E "generated.env|\.env|\.pem|\.key|__pycache__|\.DS_Store|\.bak"
```
