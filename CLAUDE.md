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
2. **Known table + column extraction** — parses `db/schema.rb` for `create_table` to build a set of real table names (`_extract_known_tables`) and a full `{table: set(columns)}` map (`_extract_schema_columns`).
3. **Scanner execution** — iterates `ALL_SCANNERS`, each produces `List[ScanResult]`. `ModelScanner` receives `known_tables` to resolve model class names accurately.
4. **Deduplication** — keeps highest-confidence result per `(file_path, line_number, reference_type)`.
5. **Reverse-association filtering** — drops `MODEL_HAS_MANY_REVERSE` and `MODEL_HAS_ONE_REVERSE` results. These arise when another model declares `has_many :table` or `has_one :singular`, meaning the **scanned table itself** holds a FK pointing to that other model's table (e.g. `rewards.business_id → businesses`). This is the opposite direction from what the scanner answers ("which tables have a FK to `<table>.id`"), so including them produces misleading evidence entries.
6. **Known-table filtering** — discards results where `table_name` isn't in `schema.rb`.
7. **Self-table exclusion** — removes results where the child table is the target table itself (the parent table shouldn't appear as its own dependency).
8. **Schema column validation** — cross-checks each `(table_name, column_name)` pair against the column map from `schema.rb`. Behaviour depends on `strict_mode`:
   - `strict_mode=False` (default): unverified results are downgraded to LOW confidence and `schema_verified=False`.
   - `strict_mode=True`: unverified results are removed entirely.
9. **Confidence filtering** — filters by user-specified minimum confidence.

### Scanner Pattern

All 7 scanners extend `BaseScanner` (in `scanners/base.py`):
- Set `applicable_categories` to declare which file types they scan.
- Implement `scan_file(path, lines, category) -> List[ScanResult]`.
- Registered in `scanners/__init__.py` via the `ALL_SCANNERS` list.

`ModelScanner` also accepts an optional `known_tables` parameter in its constructor for more accurate class-to-table resolution.

To add a new scanner: create a `BaseScanner` subclass, implement `scan_file()`, add it to `ALL_SCANNERS`.

### FK Column Derivation

The foreign key column is derived using proper Rails-style inflection from `inflection.py`. For example, `rewards` → `reward` (singular) → `reward_id`. Handles common English patterns: `-ies`, `-ses`, `-xes`, `-ches`, irregular nouns (`people` → `person`, etc.).

### ModelScanner FK Direction

The `ModelScanner` correctly handles Rails association direction:
- `belongs_to :reward` → FK lives on the **owner table** (the declaring model's table). Reports `table_name=owner, column_name=reward_id`.
- `has_many :rewards` / `has_one :reward` → FK lives on the **target table** (`rewards`). Reports `table_name=rewards, column_name={owner_singular}_id` with reference type `MODEL_HAS_MANY_REVERSE` / `MODEL_HAS_ONE_REVERSE`.

This avoids the previous false positive where `has_many :rewards` in the Checkin model would incorrectly report `checkins.reward_id` (a column that does not exist in `checkins`).

### ScanResult Fields

| Field | Description |
|-------|-------------|
| `file_path` | Path to source file |
| `line_number` | Line number of the match |
| `table_name` | Child table (table holding the FK, or target table for raw SQL) |
| `column_name` | FK column name, or empty for table-level references |
| `reference_type` | One of the `ReferenceType` enum values |
| `code_snippet` | Up to 200 chars of the matching line |
| `confidence` | `HIGH`, `MEDIUM`, or `LOW` |
| `schema_verified` | `True` if column was confirmed in `schema.rb`; `False` if not found |

### Inflection Module (inflection.py)

`src/rewards_scanner/inflection.py` provides:
- `singularize(word)` — converts plural snake_case to singular (Rails-style)
- `pluralize(word)` — converts singular to plural
- `class_name_to_table_name(class_name)` — converts `CamelCase` model names to `snake_case_plural` table names

Used by `BaseScanner.__init__` and `ModelScanner._class_to_table`.

### Web UI (server.py)

Stdlib `HTTPServer` with `daemon_threads=True` serving a single-page app from `static/index.html`.

Scans run **asynchronously** in a background thread. The frontend polls for progress and can cancel mid-scan. API routes:
- `GET /api/browse?path=...` — directory listing for path picker
- `POST /api/scan` — starts an async scan, returns immediately
- `GET /api/scan/progress` — poll for scan progress or final results
- `POST /api/scan/cancel` — cancel the running scan

`POST /api/scan` request body fields:
- `source` — `"local"` or `"github"`
- `localPath` / `repo` — path or GitHub org/repo
- `tableName` — table to scan for
- `pkColumn` — primary key column name (default `"id"`)
- `minConfidence` — `"LOW"`, `"MEDIUM"`, or `"HIGH"`
- `outputPath` — optional CSV output path
- `strictMode` — boolean; if `true`, removes results with unverified schema columns

Each result in the response includes a `schema_verified` boolean field.

The frontend deduplicates results to unique child table + column pairs for display, shows a Schema verification badge (✓ verified / ⚠ unverified) per row, and has a Strict Schema Mode toggle in the sidebar. The evidence popup shows per-evidence schema verification status with human-readable explanations.

### Progress & Cancel

The runner accepts optional `progress_cb(phase, detail)` and `cancel_check()` callbacks. Progress is reported per-file (e.g. `Scanning files... (142/830)`) for smooth progress bar updates. The frontend shows a progress bar and a Stop button during scans.

### GitHub Repo Cloning (repo.py)

Uses `gh repo clone` with `--depth 1` for shallow clones (default branch only, latest commit). This is significantly faster for large repos.

### CSV Output (output.py)

The CSV includes a `schema_verified` column in addition to the standard fields.

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
