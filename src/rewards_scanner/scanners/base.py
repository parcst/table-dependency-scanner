"""Abstract base scanner."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..inflection import singularize
from ..models import FileCategory, ScanResult


class BaseScanner(ABC):
    """Base class for all scanners."""

    # Subclasses set which file categories they handle.
    applicable_categories: List[FileCategory] = []

    def __init__(self, table_name: str, fk_column: str = ""):
        self.table_name = table_name
        # Derive the singular form using proper inflection rules
        self.singular = singularize(table_name)
        # Allow overriding the FK column name (default: singular + "_id")
        self.fk_column = fk_column or f"{self.singular}_id"

    def scan_all(
        self,
        categorized_files: Dict[FileCategory, List[Path]],
        on_file: Optional[Callable[[], None]] = None,
    ) -> List[ScanResult]:
        results = []
        for cat in self.applicable_categories:
            for path in categorized_files.get(cat, []):
                lines = self._read_file(path)
                if lines is not None:
                    results.extend(self.scan_file(path, lines, cat))
                if on_file:
                    on_file()
        return results

    @abstractmethod
    def scan_file(
        self, path: Path, lines: List[str], category: FileCategory
    ) -> List[ScanResult]:
        ...

    @staticmethod
    def _read_file(path: Path) -> List[str] | None:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            print(f"Warning: cannot read {path}: {e}", file=sys.stderr)
            return None

    def _snippet(self, line: str) -> str:
        return line.strip()[:200]
