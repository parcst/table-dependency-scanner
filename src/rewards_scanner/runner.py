"""Orchestrator: clone -> scan -> dedupe -> output -> cleanup."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from .file_collector import collect_files
from .models import Confidence, FileCategory, ScanResult
from .output import write_csv
from .repo import cleanup, clone_repo
from .scanners import ALL_SCANNERS


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


def run_scan(
    repo_path: Path,
    table_name: str,
    min_confidence: Confidence = Confidence.LOW,
    fk_column: str = "",
) -> Dict:
    """Run all scanners and return results dict (no file I/O).

    Returns dict with keys: results (List[ScanResult]), stats (dict).
    """
    categorized = collect_files(repo_path)
    total_files = sum(len(v) for v in categorized.values())

    known_tables = _extract_known_tables(categorized)

    all_results: List[ScanResult] = []
    scanner_hits: Dict[str, int] = {}
    for scanner_cls in ALL_SCANNERS:
        scanner = scanner_cls(table_name, fk_column=fk_column)
        results = scanner.scan_all(categorized)
        if results:
            scanner_hits[scanner_cls.__name__] = len(results)
        all_results.extend(results)

    deduped = _deduplicate(all_results)

    # Filter out results where the child table isn't a real database table
    if known_tables:
        deduped = [r for r in deduped if r.table_name in known_tables]

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

        scan_data = run_scan(repo_path, table_name, min_confidence)
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
