"""Parse ActiveRecord model files for reward associations."""

import re
from pathlib import Path
from typing import List

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class ModelScanner(BaseScanner):
    applicable_categories = [FileCategory.MODEL]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        results = []
        singular = self.singular
        table_name = self.table_name
        col_id = self.fk_column
        current_class = None

        class_re = re.compile(r'class\s+(\w+)\s*<')
        belongs_re = re.compile(rf'belongs_to\s+:({re.escape(singular)})\b')
        has_many_re = re.compile(rf'has_many\s+:({re.escape(table_name)})\b')
        has_one_re = re.compile(rf'has_one\s+:({re.escape(singular)})\b')

        # Indirect: belongs_to :something, class_name: 'Reward'
        indirect_re = re.compile(
            r"belongs_to\s+:(\w+).*class_name:\s*['\"]"
            + re.escape(singular.capitalize())
            + r"['\"]"
        )
        # foreign_key extraction
        fk_re = re.compile(r"foreign_key:\s*['\"](\w+)['\"]")

        # has_many :something, through: :rewards
        through_re = re.compile(
            rf'has_many\s+:(\w+)\s*,.*through:\s*:({re.escape(table_name)})\b'
        )

        for i, line in enumerate(lines, 1):
            m = class_re.search(line)
            if m:
                current_class = m.group(1)

            owner = self._class_to_table(current_class) if current_class else "unknown"

            m = through_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=col_id,
                    reference_type=ReferenceType.MODEL_HAS_MANY_THROUGH,
                    code_snippet=self._snippet(line), confidence=Confidence.MEDIUM,
                ))
                continue

            m = indirect_re.search(line)
            if m:
                fk_match = fk_re.search(line)
                col = fk_match.group(1) if fk_match else f"{m.group(1)}_id"
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=col,
                    reference_type=ReferenceType.MODEL_INDIRECT_ASSOCIATION,
                    code_snippet=self._snippet(line), confidence=Confidence.MEDIUM,
                ))
                continue

            m = belongs_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=col_id,
                    reference_type=ReferenceType.MODEL_BELONGS_TO,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = has_many_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=col_id,
                    reference_type=ReferenceType.MODEL_HAS_MANY,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            m = has_one_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=col_id,
                    reference_type=ReferenceType.MODEL_HAS_ONE,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))

        return results

    @staticmethod
    def _class_to_table(class_name: str) -> str:
        """Convert CamelCase to snake_case plural (simple heuristic)."""
        import re as _re
        s = _re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        if not s.endswith("s"):
            s += "s"
        return s
