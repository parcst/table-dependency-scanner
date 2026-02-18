# Table Dependency Scanner

Scans a Rails/Ruby codebase to find all references and dependencies on a given database table. Identifies child tables, foreign key columns, polymorphic associations, raw SQL references, model associations, and migration history.

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)
- `gh` CLI required for GitHub repo cloning (optional)

## Quick Start

### Web UI

```bash
cd table-dependency-scanner
python3 run.py
```

Opens a browser to `http://localhost:8642` where you can:
- Select a local directory or GitHub repo
- Set the target table name and primary key
- Choose a minimum confidence level
- View results as a sortable table
- Optionally export to CSV

### CLI

```bash
cd table-dependency-scanner

# Scan a local Rails repo
PYTHONPATH=src python3 -m rewards_scanner --local-path /path/to/rails/app --table-name rewards

# Scan a GitHub repo
PYTHONPATH=src python3 -m rewards_scanner --repo org/repo --table-name users

# Filter by confidence and save to CSV
PYTHONPATH=src python3 -m rewards_scanner --local-path /path/to/app --table-name orders --min-confidence MEDIUM --output results.csv
```

### Install as a package (optional)

```bash
cd table-dependency-scanner
pip install -e .

# Then use the CLI directly
table-scan --local-path /path/to/rails/app --table-name rewards
table-scan --repo org/repo --table-name users --output results.csv
```

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--local-path` | Path to a local Rails codebase | *(required, or use --repo)* |
| `--repo` | GitHub repo to clone (`org/repo`) | *(required, or use --local-path)* |
| `--table-name` | Database table to scan for | `rewards` |
| `--min-confidence` | Minimum confidence: `HIGH`, `MEDIUM`, `LOW` | `LOW` |
| `--output` | Output CSV file path | stdout |
| `--keep-clone` | Don't delete temp clone after scan | `false` |

## What It Detects

| Scanner | What it finds | Confidence |
|---------|--------------|------------|
| **Schema** | Column definitions and references in `db/schema.rb` | HIGH |
| **Migration** | `add_reference`, `add_column`, `add_foreign_key` in migrations | HIGH |
| **Model** | `belongs_to`, `has_many`, `has_one` associations | HIGH |
| **Polymorphic** | Polymorphic `_type`/`_id` pairs confirmed by model `as:` declarations | HIGH |
| **Polymorphic** | Polymorphic pairs with code evidence (e.g. `owner_type: "Reward"`) | MEDIUM |
| **Raw SQL** | Direct table/column references in SQL strings, joins, interpolations | HIGH-LOW |
| **Config** | Table name references in YAML config files | LOW |
| **Contextual** | Variable names, comments, and heuristic matches | LOW |

## Project Structure

```
table-dependency-scanner/
├── pyproject.toml
├── README.md
└── src/rewards_scanner/
    ├── __init__.py
    ├── __main__.py          # CLI entry point
    ├── cli.py               # Argument parsing
    ├── runner.py             # Scan orchestrator
    ├── models.py             # Data models (ScanResult, Confidence, etc.)
    ├── output.py             # CSV writer
    ├── file_collector.py     # File categorization
    ├── repo.py               # GitHub clone/cleanup
    ├── server.py             # Web UI HTTP server
    ├── static/
    │   └── index.html        # Web UI frontend
    └── scanners/
        ├── base.py               # Abstract base scanner
        ├── schema_scanner.py     # schema.rb parser
        ├── migration_scanner.py  # Migration file parser
        ├── model_scanner.py      # ActiveRecord model parser
        ├── polymorphic_scanner.py# Polymorphic association detector
        ├── raw_sql_scanner.py    # Raw SQL reference finder
        ├── config_scanner.py     # YAML config scanner
        └── contextual_scanner.py # Heuristic catch-all
```
