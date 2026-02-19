"""CSV output writer."""

from __future__ import annotations

import csv
import sys
from typing import IO, List, Optional

from .models import ScanResult

COLUMNS = [
    "file_path",
    "line_number",
    "table_name",
    "column_name",
    "reference_type",
    "code_snippet",
    "confidence",
    "schema_verified",
]


def write_csv(results: List[ScanResult], dest: IO[str] | None = None):
    """Write results as CSV. If dest is None, write to stdout."""
    out = dest or sys.stdout
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for r in results:
        writer.writerow([
            r.file_path,
            r.line_number,
            r.table_name,
            r.column_name,
            r.reference_type.value,
            r.code_snippet,
            r.confidence.value,
            r.schema_verified,
        ])
