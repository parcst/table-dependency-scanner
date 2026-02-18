"""Heuristic catch-all scanner for contextual reward references."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class ContextualScanner(BaseScanner):
    applicable_categories = [
        FileCategory.RUBY_OTHER,
        FileCategory.MODEL,
        FileCategory.ERB,
        FileCategory.SQL,
    ]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        singular = self.singular
        table_name = self.table_name

        # Variable/method names that look reward-related
        var_re = re.compile(rf'\b{re.escape(singular)}[s]?[\w]*\b', re.IGNORECASE)
        # Query-adjacent keywords
        query_re = re.compile(
            r'\b(query|execute|select|where|find_by|pluck|update_all|delete_all|sql|connection)\b',
            re.IGNORECASE,
        )
        # Comment mentioning rewards + schema keywords
        comment_re = re.compile(r'#.*\b' + re.escape(singular), re.IGNORECASE)
        schema_kw_re = re.compile(
            r'\b(table|column|foreign[_ ]?key|fk|migration|schema|index)\b',
            re.IGNORECASE,
        )

        for i, line in enumerate(lines, 1):
            # Variable near query code
            if var_re.search(line) and query_re.search(line):
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=table_name, column_name="",
                    reference_type=ReferenceType.CONTEXTUAL_VARIABLE,
                    code_snippet=self._snippet(line),
                    confidence=Confidence.LOW,
                ))
                continue

            # Comment mentioning rewards + schema keywords
            if comment_re.search(line) and schema_kw_re.search(line):
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=table_name, column_name="",
                    reference_type=ReferenceType.CONTEXTUAL_COMMENT,
                    code_snippet=self._snippet(line),
                    confidence=Confidence.LOW,
                ))

        return results
