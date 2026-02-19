"""Parse ActiveRecord model files for reward associations."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..inflection import class_name_to_table_name, singularize
from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class ModelScanner(BaseScanner):
    applicable_categories = [FileCategory.MODEL]

    def __init__(self, table_name: str, fk_column: str = "", known_tables: Optional[Set[str]] = None):
        super().__init__(table_name, fk_column)
        # Used to resolve model class names -> real table names via schema.rb
        self._known_tables: Set[str] = known_tables or set()

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
            # Derive the FK that the owner table would hold if it belongs_to target
            owner_singular = singularize(owner)
            owner_fk = f"{owner_singular}_id"

            # has_many :something, through: :rewards
            # The owner does NOT hold the FK -- this is a join-table traversal.
            # Report as a reference on the target (rewards) side with no specific FK column.
            m = through_re.search(line)
            if m:
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name="",
                    reference_type=ReferenceType.MODEL_HAS_MANY_THROUGH,
                    code_snippet=self._snippet(line), confidence=Confidence.MEDIUM,
                ))
                continue

            # belongs_to :something, class_name: 'Reward'
            # The owner table holds the FK column (e.g. something_id or explicit foreign_key:)
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

            # belongs_to :reward  →  FK (reward_id) lives on the OWNER table
            m = belongs_re.search(line)
            if m:
                # Check for explicit foreign_key: option
                fk_match = fk_re.search(line)
                actual_col = fk_match.group(1) if fk_match else col_id
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=owner, column_name=actual_col,
                    reference_type=ReferenceType.MODEL_BELONGS_TO,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            # has_many :rewards  →  FK ({owner_singular}_id) lives on the TARGET table (rewards)
            # This is the REVERSE direction: we report on the target table, not the owner.
            m = has_many_re.search(line)
            if m:
                # Check for explicit foreign_key: option
                fk_match = fk_re.search(line)
                actual_col = fk_match.group(1) if fk_match else owner_fk
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=table_name, column_name=actual_col,
                    reference_type=ReferenceType.MODEL_HAS_MANY_REVERSE,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))
                continue

            # has_one :reward  →  FK ({owner_singular}_id) lives on the TARGET table (rewards)
            m = has_one_re.search(line)
            if m:
                fk_match = fk_re.search(line)
                actual_col = fk_match.group(1) if fk_match else owner_fk
                results.append(ScanResult(
                    file_path=str(path), line_number=i,
                    table_name=table_name, column_name=actual_col,
                    reference_type=ReferenceType.MODEL_HAS_ONE_REVERSE,
                    code_snippet=self._snippet(line), confidence=Confidence.HIGH,
                ))

        return results

    def _class_to_table(self, class_name: str) -> str:
        """Convert a CamelCase model class name to a snake_case table name.

        Strategy:
        1. Convert to snake_case plural via inflection.
        2. If the result matches a known table from schema.rb, use it directly.
        3. Otherwise, try common suffixes/prefixes that Rails STI may produce and fall
           back to the naive snake_case plural.
        """
        if not class_name:
            return "unknown"

        candidate = class_name_to_table_name(class_name)

        if not self._known_tables:
            return candidate

        if candidate in self._known_tables:
            return candidate

        # Try stripping common module-like prefixes that appear as nested namespaces
        # e.g. Admin::User -> users (strip "admin_" prefix)
        parts = candidate.split("_")
        for i in range(1, len(parts)):
            tail = "_".join(parts[i:])
            if tail in self._known_tables:
                return tail

        # Fall back to the original candidate even if not in known_tables
        return candidate
