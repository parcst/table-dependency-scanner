"""Scan YAML config files for table name references."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class ConfigScanner(BaseScanner):
    applicable_categories = [FileCategory.YML]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        table_name = self.table_name
        singular = self.singular

        # Skip database.yml — table names there are DB names, not references
        if path.name == "database.yml":
            return results

        table_re = re.compile(rf'\b{re.escape(table_name)}\b')
        comment_re = re.compile(r'^\s*#')

        for i, line in enumerate(lines, 1):
            if comment_re.match(line):
                continue
            if table_re.search(line):
                # Determine confidence: key-value with table name is MEDIUM, else LOW
                if re.search(rf':\s*{re.escape(table_name)}\b', line):
                    confidence = Confidence.MEDIUM
                elif re.search(rf'\b{re.escape(singular)}_', line):
                    confidence = Confidence.MEDIUM
                else:
                    confidence = Confidence.LOW

                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=table_name, column_name="",
                    reference_type=ReferenceType.CONFIG_TABLE_REF,
                    code_snippet=self._snippet(line),
                    confidence=confidence,
                ))

        return results
