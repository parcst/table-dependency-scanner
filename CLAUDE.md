# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

### Web UI
```bash
python3 run.py
```
Starts an HTTP server on `http://localhost:8642` and auto-opens a browser.

### CLI (without installing)
```bash
PYTHONPATH=src python3 -m rewards_scanner --local-path /path/to/rails/app --table-name rewards
PYTHONPATH=src python3 -m rewards_scanner --repo org/repo --table-name users --output results.csv
```

### CLI (installed as package)
```bash
pip install -e .
table-scan --local-path /path/to/rails/app --table-name rewards
```

## Key Details

- Python 3.10+, **zero external dependencies** (stdlib only)
- `gh` CLI required only for GitHub repo cloning
- Web UI port is hardcoded to 8642
- No test suite exists

## Architecture

The scanner analyzes a Rails codebase to find all references and dependencies on a given database table.

### Pipeline (runner.py)

`run_scan()` orchestrates everything in this order:

1. **File collection** (`file_collector.py`) — walks the repo, categorizes files into `FileCategory` enums (SCHEMA, MIGRATION, MODEL, RUBY_OTHER, SQL, ERB, YML). Skips `vendor/`, `node_modules/`, `.git/`, `tmp/`, `log/`.
2. **Known table extraction** — parses `db/schema.rb` for `create_table` to build a set of real database table names.
3. **Scanner execution** — iterates `ALL_SCANNERS`, each produces `List[ScanResult]`.
4. **Deduplication** — keeps highest-confidence result per `(file_path, line_number, reference_type)`.
5. **Known-table filtering** — discards results where `table_name` isn't in `schema.rb`.
6. **Confidence filtering** — filters by user-specified minimum confidence.

### Scanner Pattern

All 7 scanners extend `BaseScanner` (in `scanners/base.py`):
- Set `applicable_categories` to declare which file types they scan.
- Implement `scan_file(path, lines, category) -> List[ScanResult]`.
- Registered in `scanners/__init__.py` via the `ALL_SCANNERS` list.

To add a new scanner: create a `BaseScanner` subclass, implement `scan_file()`, add it to `ALL_SCANNERS`.

### FK Column Derivation

The foreign key column is derived by stripping trailing 's' from the table name and appending `_id`. For example, `rewards` → `reward_id`. This is a simple heuristic, not Rails inflection.

### Web UI (server.py)

Stdlib `HTTPServer` serving a single-page app from `static/index.html`. API routes:
- `GET /api/browse?path=...` — directory listing for path picker
- `POST /api/scan` — runs scan, returns JSON results + stats

The frontend deduplicates results to unique child table + column pairs for display, with an evidence popup showing all matching references per pair.

## Maintenance Rule

**Keep this file up to date.** When making changes to this codebase, update CLAUDE.md to reflect:
- New or removed scanners (update the scanner count and pattern section)
- Changes to the pipeline steps in `runner.py`
- New API routes or server changes
- New CLI flags or entry points
- New dependencies or Python version requirements
- Changes to the web UI architecture (e.g., new modals, data flow changes)
- Addition of a test suite or build tooling

Do this as part of the same commit that introduces the change.
