"""Walk a repo and categorize files for scanning."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .models import FileCategory

SKIP_DIRS = {"vendor", "node_modules", ".git", "tmp", "log"}


def collect_files(repo_path: Path) -> Dict[FileCategory, List[Path]]:
    """Walk repo_path and return files grouped by category."""
    categorized: Dict[FileCategory, List[Path]] = {cat: [] for cat in FileCategory}

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded directories
        if any(part in SKIP_DIRS for part in path.relative_to(repo_path).parts):
            continue

        cat = _categorize(path, repo_path)
        if cat is not None:
            categorized[cat].append(path)

    return categorized


def _categorize(path: Path, repo_root: Path) -> FileCategory | None:
    rel = path.relative_to(repo_root)
    parts = rel.parts
    suffix = path.suffix

    # schema.rb
    if parts == ("db", "schema.rb"):
        return FileCategory.SCHEMA

    # migrations
    if len(parts) >= 2 and parts[0] == "db" and parts[1] == "migrate" and suffix == ".rb":
        return FileCategory.MIGRATION

    # models (app/models/ and concerns)
    if len(parts) >= 2 and parts[0] == "app" and parts[1] == "models" and suffix == ".rb":
        return FileCategory.MODEL

    if suffix == ".rb":
        return FileCategory.RUBY_OTHER
    if suffix == ".sql":
        return FileCategory.SQL
    if suffix == ".erb":
        return FileCategory.ERB
    if suffix in (".yml", ".yaml"):
        return FileCategory.YML

    return None
