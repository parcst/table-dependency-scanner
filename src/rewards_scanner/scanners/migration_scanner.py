"""Parse migration files for reward references."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class MigrationScanner(BaseScanner):
    applicable_categories = [FileCategory.MIGRATION]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        singular = self.singular
        table_name = self.table_name
        col_id = self.fk_column
        current_table = None

        create_re = re.compile(r'create_table\s+[:"]([\w]+)')

        add_ref_re = re.compile(
            rf'add_reference\s+:(\w+)\s*,\s*:({re.escape(singular)})\b'
        )
        add_col_re = re.compile(
            rf'add_column\s+:(\w+)\s*,\s*:({re.escape(col_id)})\s*,'
        )
        add_fk_re = re.compile(
            rf'add_foreign_key\s+:(\w+)\s*,\s*:({re.escape(table_name)})\b'
        )
        t_ref_re = re.compile(
            rf't\.references\s+:({re.escape(singular)})\b'
        )
        remove_ref_re = re.compile(
            rf'remove_reference\s+:(\w+)\s*,\s*:({re.escape(singular)})\b'
        )
        remove_col_re = re.compile(
            rf'remove_column\s+:(\w+)\s*,\s*:({re.escape(col_id)})\b'
        )

        for i, line in enumerate(lines, 1):
            m = create_re.search(line)
            if m:
                current_table = m.group(1)

            if line.strip() == "end":
                pass  # Don't reset — migrations can have nested blocks

            m = add_ref_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=m.group(1), column_name=col_id,
                    reference_type=ReferenceType.MIGRATION_ADD_REFERENCE,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = add_col_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=m.group(1), column_name=col_id,
                    reference_type=ReferenceType.MIGRATION_ADD_COLUMN,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = add_fk_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=m.group(1), column_name=col_id,
                    reference_type=ReferenceType.MIGRATION_ADD_FOREIGN_KEY,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = t_ref_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=current_table or "unknown", column_name=col_id,
                    reference_type=ReferenceType.MIGRATION_CREATE_TABLE_REF,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = remove_ref_re.search(line) or remove_col_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=m.group(1), column_name=col_id,
                    reference_type=ReferenceType.MIGRATION_REMOVE,
                    code_snippet=self._snippet(line), confidence=Confidence.MEDIUM,
                ))

        return results
