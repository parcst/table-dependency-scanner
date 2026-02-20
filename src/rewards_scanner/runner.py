"""Orchestrator: clone -> scan -> dedupe -> output -> cleanup."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from .file_collector import collect_files
from .models import Confidence, FileCategory, ReferenceType, ScanResult
from .output import write_csv
from .repo import cleanup, clone_repo
from .scanners import ALL_SCANNERS
from .scanners.model_scanner import ModelScanner


def _extract_known_tables(categorized: Dict[FileCategory, List[Path]]) -> Set[str]:
    """Parse schema.rb to get the set of real database table names."""
    tables: Set[str] = set()
    create_re = re.compile(r'create_table\s+"(\w+)"')
    for path in categorized.get(FileCategory.SCHEMA, []):
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                m = create_re.search(line)
                if m:
                    tables.add(m.group(1))
        except OSError:
            pass
    return tables


def _extract_schema_columns(categorized: Dict[FileCategory, List[Path]]) -> Dict[str, Dict[str, str]]:
    """Parse schema.rb to build a mapping of table_name -> {column_name: datatype}.

    Parses every `create_table` block and collects column names and types from lines like:
        t.integer "column_name", ...
        t.string "column_name", ...
        t.references :column_name, ...  (stored as column_name_id and column_name_type)
    """
    schema_columns: Dict[str, Dict[str, str]] = {}
    current_table: Optional[str] = None

    create_re = re.compile(r'create_table\s+"(\w+)"')
    # Matches: t.<type> "col_name" or t.<type> :col_name
    col_re = re.compile(r'\bt\.(\w+)\s+[":]([\w]+)')

    for path in categorized.get(FileCategory.SCHEMA, []):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for line in lines:
            m = create_re.search(line)
            if m:
                current_table = m.group(1)
                schema_columns.setdefault(current_table, {})
                continue

            if current_table is None:
                continue

            m = col_re.search(line)
            if not m:
                continue

            col_type = m.group(1)
            col_name = m.group(2)

            # Skip non-column DSL keywords that match the pattern
            if col_type in ("index", "timestamps", "primary_key"):
                continue

            if col_type == "references":
                # t.references :user  expands to user_id + user_type (if polymorphic)
                schema_columns[current_table][f"{col_name}_id"] = "bigint"
                if "polymorphic:" in line or "polymorphic: true" in line:
                    schema_columns[current_table][f"{col_name}_type"] = "string"
            else:
                schema_columns[current_table][col_name] = col_type

    return schema_columns


def _validate_schema_columns(
    results: List[ScanResult],
    schema_columns: Dict[str, Dict[str, str]],
    strict_mode: bool,
) -> List[ScanResult]:
    """Cross-check each result's (table_name, column_name) against schema.rb.

    - strict_mode=True:  remove results where the column is not found in the table.
    - strict_mode=False: downgrade confidence to LOW and set schema_verified=False.
    - Attaches column_datatype from schema.rb when available.

    Results with empty column_name are skipped (table-level references have no column to check).
    Results for tables not present in schema are left unchanged (they were already filtered
    by the known-table pass upstream, or schema.rb wasn't available).
    """
    validated: List[ScanResult] = []
    for r in results:
        # Nothing to validate when column is unknown/empty
        if not r.column_name:
            validated.append(r)
            continue

        # Table not in schema map -> schema.rb unavailable, pass through
        if r.table_name not in schema_columns:
            validated.append(r)
            continue

        table_cols = schema_columns[r.table_name]
        if r.column_name in table_cols:
            # Column confirmed present — attach datatype
            r.column_datatype = table_cols[r.column_name]
            validated.append(r)
        else:
            # Column NOT present in schema
            if strict_mode:
                # Drop entirely
                pass
            else:
                r.schema_verified = False
                # Downgrade to LOW regardless of original confidence
                r.confidence = Confidence.LOW
                validated.append(r)

    return validated


def run_scan(
    repo_path: Path,
    table_name: str,
    min_confidence: Confidence = Confidence.LOW,
    fk_column: str = "",
    strict_mode: bool = False,
    progress_cb: Optional[Callable[[str, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict:
    """Run all scanners and return results dict (no file I/O).

    Returns dict with keys: results (List[ScanResult]), stats (dict).
    progress_cb(phase, detail) is called to report progress.
    cancel_check() should return True if the scan should abort.
    """
    def _progress(phase: str, detail: str = ""):
        if progress_cb:
            progress_cb(phase, detail)

    def _cancelled() -> bool:
        return cancel_check() if cancel_check else False

    _progress("collecting", "Collecting files...")
    categorized = collect_files(repo_path)
    total_files = sum(len(v) for v in categorized.values())

    if _cancelled():
        return {"results": [], "stats": {}}

    _progress("parsing_schema", "Parsing schema.rb...")
    known_tables = _extract_known_tables(categorized)
    schema_columns = _extract_schema_columns(categorized)

    if _cancelled():
        return {"results": [], "stats": {}}

    # Calculate total files across all scanners for accurate progress
    scan_file_count = 0
    for scanner_cls in ALL_SCANNERS:
        for cat in scanner_cls.applicable_categories:
            scan_file_count += len(categorized.get(cat, []))

    all_results: List[ScanResult] = []
    scanner_hits: Dict[str, int] = {}
    files_processed = 0

    def _on_file():
        nonlocal files_processed
        files_processed += 1
        _progress("scanning", f"Scanning files... ({files_processed}/{scan_file_count})")

    for scanner_cls in ALL_SCANNERS:
        if _cancelled():
            return {"results": [], "stats": {}}
        if scanner_cls is ModelScanner:
            scanner = scanner_cls(table_name, fk_column=fk_column, known_tables=known_tables)
        else:
            scanner = scanner_cls(table_name, fk_column=fk_column)
        results = scanner.scan_all(categorized, on_file=_on_file)
        if results:
            scanner_hits[scanner_cls.__name__] = len(results)
        all_results.extend(results)

    if _cancelled():
        return {"results": [], "stats": {}}

    _progress("processing", "Deduplicating and filtering results...")
    deduped = _deduplicate(all_results)

    # Remove reverse-direction association results.
    # MODEL_HAS_MANY_REVERSE / MODEL_HAS_ONE_REVERSE arise when some other model declares
    # `has_many :table_name` or `has_one :singular`, meaning the scanned table holds a FK
    # pointing back to that other model's table (e.g. rewards.business_id → businesses).
    # That is the opposite of what we are scanning for ("who has a FK to <table>.id"), so
    # including them causes misleading "Evidence for rewards.business_id" entries in the UI.
    _REVERSE_TYPES = {ReferenceType.MODEL_HAS_MANY_REVERSE, ReferenceType.MODEL_HAS_ONE_REVERSE}
    deduped = [r for r in deduped if r.reference_type not in _REVERSE_TYPES]

    # Filter out results where the child table isn't a real database table
    if known_tables:
        deduped = [r for r in deduped if r.table_name in known_tables]

    # Exclude the target table itself — it's the parent, not a child dependency
    deduped = [r for r in deduped if r.table_name != table_name]

    # Validate (table, column) pairs against schema.rb column map
    if schema_columns:
        deduped = _validate_schema_columns(deduped, schema_columns, strict_mode=strict_mode)

    filtered = [r for r in deduped if r.confidence >= min_confidence]

    confidence_order = {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}
    filtered.sort(key=lambda r: (confidence_order[r.confidence], r.file_path, r.line_number))

    # Strip repo_path prefix for cleaner output
    for r in filtered:
        if r.file_path.startswith(str(repo_path)):
            r.file_path = r.file_path[len(str(repo_path)):].lstrip("/")

    return {
        "results": filtered,
        "stats": {
            "total_files_scanned": total_files,
            "raw_hits": len(all_results),
            "after_dedup": len(deduped),
            "after_schema_validation": len(deduped),  # already filtered in-place above
            "after_filter": len(filtered),
            "scanner_hits": scanner_hits,
        },
    }


def run(
    repo: str | None,
    local_path: str | None,
    output: str | None,
    keep_clone: bool,
    min_confidence: Confidence,
    table_name: str,
    strict_mode: bool = False,
):
    cloned_path = None
    try:
        if repo:
            repo_path = clone_repo(repo)
            cloned_path = repo_path.parent  # temp dir containing "repo/"
        else:
            repo_path = Path(local_path)
            if not repo_path.is_dir():
                print(f"Error: {local_path} is not a directory.", file=sys.stderr)
                sys.exit(1)

        print(f"Scanning {repo_path} for '{table_name}' references...", file=sys.stderr)

        scan_data = run_scan(repo_path, table_name, min_confidence, strict_mode=strict_mode)
        filtered = scan_data["results"]
        stats = scan_data["stats"]

        print(f"Found {stats['total_files_scanned']} scannable files.", file=sys.stderr)
        for name, count in stats["scanner_hits"].items():
            print(f"  {name}: {count} hits", file=sys.stderr)
        print(f"\n{stats['after_filter']} results (min confidence: {min_confidence.value}).", file=sys.stderr)

        # Write output
        if output:
            with open(output, "w", newline="") as f:
                write_csv(filtered, f)
            print(f"Results written to {output}", file=sys.stderr)
        else:
            write_csv(filtered)

    finally:
        if cloned_path and not keep_clone:
            print("Cleaning up temp clone...", file=sys.stderr)
            cleanup(cloned_path)


def _deduplicate(results: List[ScanResult]) -> List[ScanResult]:
    best = {}
    for r in results:
        key = r.dedup_key
        if key not in best or r.confidence > best[key].confidence:
            best[key] = r
    return list(best.values())
