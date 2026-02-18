"""Parse schema.rb for reward column references."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class SchemaScanner(BaseScanner):
    applicable_categories = [FileCategory.SCHEMA]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        current_table = None
        singular = self.singular
        table_name = self.table_name
        col_id = self.fk_column

        create_re = re.compile(r'create_table\s+"(\w+)"')
        col_re = re.compile(
            rf't\.(integer|bigint|references)\s+"?:?({re.escape(singular)}(?:_id)?)"?'
        )
        ref_re = re.compile(rf't\.references\s+:({re.escape(singular)})\b')

        for i, line in enumerate(lines, 1):
            m = create_re.search(line)
            if m:
                current_table = m.group(1)

            if ref_re.search(line):
                results.append(ScanResult(
                    file_path=str(path),
                    line_number=i,
                    table_name=current_table or "unknown",
                    column_name=col_id,
                    reference_type=ReferenceType.SCHEMA_REFERENCE,
                    code_snippet=self._snippet(line),
                    confidence=Confidence.HIGH,
                ))
                continue

            m = col_re.search(line)
            if m:
                col_type, col_name = m.group(1), m.group(2)
                if col_type == "references":
                    continue  # handled above
                if col_name == singular:
                    col_name = col_id
                results.append(ScanResult(
                    file_path=str(path),
                    line_number=i,
                    table_name=current_table or "unknown",
                    column_name=col_name,
                    reference_type=ReferenceType.SCHEMA_COLUMN,
                    code_snippet=self._snippet(line),
                    confidence=Confidence.HIGH,
                ))

        return results
