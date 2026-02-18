"""Scan for raw SQL references to the rewards table."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class RawSqlScanner(BaseScanner):
    applicable_categories = [
        FileCategory.RUBY_OTHER,
        FileCategory.MODEL,
        FileCategory.ERB,
        FileCategory.SQL,
        FileCategory.MIGRATION,
    ]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        singular = self.singular
        table_name = self.table_name
        col_id = self.fk_column

        # Precompile patterns
        # HIGH: rewards.id or reward_id in SQL-like context
        col_ref_re = re.compile(
            rf'\b{re.escape(table_name)}\.id\b|(?<!\w){re.escape(col_id)}(?!\w)',
            re.IGNORECASE,
        )
        # HIGH: FROM/UPDATE/INSERT INTO/DELETE FROM rewards
        table_dml_re = re.compile(
            rf'\b(?:FROM|UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+[`"]?{re.escape(table_name)}[`"]?\b',
            re.IGNORECASE,
        )
        # MEDIUM: JOIN rewards ON ...
        join_re = re.compile(
            rf'\bJOIN\s+[`"]?{re.escape(table_name)}[`"]?\s+ON\s+(\w+)\.(\w+)\s*=\s*{re.escape(table_name)}\.(\w+)',
            re.IGNORECASE,
        )
        # MEDIUM: .where/.joins/.includes referencing rewards
        query_method_re = re.compile(
            rf'\.(where|joins|includes|eager_load|preload|references)\b.*[:(\'\"]{re.escape(singular)}',
            re.IGNORECASE,
        )
        # LOW: string interpolation near reward
        interp_re = re.compile(
            rf'#\{{.*{re.escape(singular)}.*\}}',
            re.IGNORECASE,
        )

        in_heredoc = False
        heredoc_content: List[str] = []
        heredoc_start_line = 0
        heredoc_end_re = None

        for i, line in enumerate(lines, 1):
            # Track heredoc SQL blocks
            if not in_heredoc:
                hd_match = re.search(r'<<[-~]?(\w*SQL\w*)', line)
                if hd_match:
                    in_heredoc = True
                    heredoc_content = []
                    heredoc_start_line = i
                    heredoc_end_re = re.compile(rf'^\s*{re.escape(hd_match.group(1))}\s*$')

            if in_heredoc:
                heredoc_content.append(line)
                if heredoc_end_re and heredoc_end_re.match(line) and i > heredoc_start_line:
                    # Scan the full heredoc block
                    full_sql = "\n".join(heredoc_content)
                    results.extend(
                        self._scan_sql_block(path, heredoc_start_line, full_sql, table_name, singular, col_id)
                    )
                    in_heredoc = False
                    heredoc_content = []
                continue

            # Scan individual line
            results.extend(self._scan_line(
                path, i, line, col_ref_re, table_dml_re, join_re,
                query_method_re, interp_re, table_name, singular, col_id,
            ))

        return results

    def _scan_line(
        self, path, i, line, col_ref_re, table_dml_re, join_re,
        query_method_re, interp_re, table_name, singular, col_id,
    ) -> List[ScanResult]:
        results = []
        snippet = self._snippet(line)

        m = join_re.search(line)
        if m:
            child_table, child_col, _ = m.group(1), m.group(2), m.group(3)
            results.append(ScanResult(
                file_path=str(path), line_number=i,
                table_name=child_table, column_name=child_col,
                reference_type=ReferenceType.RAW_SQL_JOIN,
                code_snippet=snippet, confidence=Confidence.MEDIUM,
            ))
            return results

        if table_dml_re.search(line):
            results.append(ScanResult(
                file_path=str(path), line_number=i,
                table_name=table_name, column_name="",
                reference_type=ReferenceType.RAW_SQL_TABLE_REF,
                code_snippet=snippet, confidence=Confidence.HIGH,
            ))
            return results

        if col_ref_re.search(line):
            results.append(ScanResult(
                file_path=str(path), line_number=i,
                table_name=table_name, column_name=col_id,
                reference_type=ReferenceType.RAW_SQL_COLUMN_REF,
                code_snippet=snippet, confidence=Confidence.HIGH,
            ))
            return results

        if query_method_re.search(line):
            results.append(ScanResult(
                file_path=str(path), line_number=i,
                table_name=table_name, column_name="",
                reference_type=ReferenceType.RAW_SQL_QUERY_METHOD,
                code_snippet=snippet, confidence=Confidence.MEDIUM,
            ))
            return results

        if interp_re.search(line):
            results.append(ScanResult(
                file_path=str(path), line_number=i,
                table_name=table_name, column_name="",
                reference_type=ReferenceType.RAW_SQL_INTERPOLATION,
                code_snippet=snippet, confidence=Confidence.LOW,
            ))

        return results

    def _scan_sql_block(
        self, path, start_line, sql_block, table_name, singular, col_id
    ) -> List[ScanResult]:
        """Scan a multi-line heredoc SQL block."""
        results = []
        join_re = re.compile(
            rf'\bJOIN\s+[`"]?{re.escape(table_name)}[`"]?\s+ON\s+(\w+)\.(\w+)\s*=\s*{re.escape(table_name)}\.(\w+)',
            re.IGNORECASE,
        )
        table_dml_re = re.compile(
            rf'\b(?:FROM|UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+[`"]?{re.escape(table_name)}[`"]?\b',
            re.IGNORECASE,
        )
        col_ref_re = re.compile(
            rf'\b{re.escape(table_name)}\.id\b|(?<!\w){re.escape(col_id)}(?!\w)',
            re.IGNORECASE,
        )

        snippet = sql_block.strip()[:200]

        m = join_re.search(sql_block)
        if m:
            results.append(ScanResult(
                file_path=str(path), line_number=start_line,
                table_name=m.group(1), column_name=m.group(2),
                reference_type=ReferenceType.RAW_SQL_JOIN,
                code_snippet=snippet, confidence=Confidence.MEDIUM,
            ))

        if table_dml_re.search(sql_block):
            results.append(ScanResult(
                file_path=str(path), line_number=start_line,
                table_name=table_name, column_name="",
                reference_type=ReferenceType.RAW_SQL_TABLE_REF,
                code_snippet=snippet, confidence=Confidence.HIGH,
            ))

        if col_ref_re.search(sql_block):
            results.append(ScanResult(
                file_path=str(path), line_number=start_line,
                table_name=table_name, column_name=col_id,
                reference_type=ReferenceType.RAW_SQL_COLUMN_REF,
                code_snippet=snippet, confidence=Confidence.HIGH,
            ))

        return results
