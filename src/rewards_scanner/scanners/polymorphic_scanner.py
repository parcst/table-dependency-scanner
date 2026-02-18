"""Detect polymorphic associations that may reference the target table."""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..models import Confidence, FileCategory, ReferenceType, ScanResult
from .base import BaseScanner


class PolymorphicScanner(BaseScanner):
    applicable_categories = [FileCategory.SCHEMA, FileCategory.MODEL]

    def scan_file(self, path: Path, lines: List[str], category: FileCategory) -> List[ScanResult]:
        return []  # Not used — scan_all is overridden

    def scan_all(self, categorized_files: Dict[FileCategory, List[Path]]) -> List[ScanResult]:
        """Three-pass approach:
        1. Parse schema.rb for polymorphic _type/_id column pairs
        2. Check model files for `has_many/has_one :table, as: :poly` (HIGH)
        3. Search all code for evidence linking the _type to the target model (MEDIUM)
        Only report pairs with evidence from pass 2 or 3.
        """
        table_name = self.table_name
        singular = self.singular
        # CamelCase model class: "reward" -> "Reward", "reward_credit" -> "RewardCredit"
        model_class = "".join(w.capitalize() for w in singular.split("_"))

        # Pass 1: find all polymorphic _type/_id pairs in schema
        poly_pairs: Dict[Tuple[str, str], Tuple[int, str]] = {}
        for schema_path in categorized_files.get(FileCategory.SCHEMA, []):
            lines = self._read_file(schema_path)
            if not lines:
                continue
            current_table = None
            type_cols: Dict[str, int] = {}
            id_cols: Dict[str, Tuple[int, str]] = {}

            for i, line in enumerate(lines, 1):
                m = re.search(r'create_table\s+"(\w+)"', line)
                if m:
                    if current_table:
                        for prefix in type_cols:
                            if prefix in id_cols:
                                poly_pairs[(current_table, prefix)] = id_cols[prefix]
                    current_table = m.group(1)
                    type_cols = {}
                    id_cols = {}
                    continue

                if current_table and current_table != table_name:
                    tm = re.search(r't\.string\s+"(\w+)_type"', line)
                    if tm:
                        type_cols[tm.group(1)] = i

                    im = re.search(r't\.(integer|bigint)\s+"(\w+)_id"', line)
                    if im:
                        id_cols[im.group(2)] = (i, self._snippet(line))

            if current_table:
                for prefix in type_cols:
                    if prefix in id_cols:
                        poly_pairs[(current_table, prefix)] = id_cols[prefix]

        if not poly_pairs:
            return []

        # Pass 2: check model files for `has_many/has_one :table, as: :prefix` (HIGH)
        confirmed_prefixes: Set[str] = set()
        for model_path in categorized_files.get(FileCategory.MODEL, []):
            model_lines = self._read_file(model_path)
            if not model_lines:
                continue
            for line in model_lines:
                m = re.search(
                    rf'(?:has_many|has_one)\s+:({re.escape(table_name)}|{re.escape(singular)})\s*,.*as:\s*:(\w+)',
                    line,
                )
                if m:
                    confirmed_prefixes.add(m.group(2))

        # Pass 3: search all code files for evidence linking a polymorphic _type
        # to the target model class. E.g.:
        #   owner_type: "Reward"
        #   owner_type => "Reward"
        #   WHERE owner_type = 'Reward'
        #   .where(owner_type: 'Reward')
        # We look for each unconfirmed prefix's _type column near the model class name.
        unconfirmed_prefixes = {
            prefix for (_, prefix) in poly_pairs if prefix not in confirmed_prefixes
        }
        evidence_prefixes: Set[str] = set()

        if unconfirmed_prefixes:
            # Build a regex that matches any of the prefixes' _type near the model class
            all_code_categories = [
                FileCategory.MODEL, FileCategory.RUBY_OTHER, FileCategory.ERB,
                FileCategory.SQL, FileCategory.MIGRATION,
            ]
            for cat in all_code_categories:
                for file_path in categorized_files.get(cat, []):
                    file_lines = self._read_file(file_path)
                    if not file_lines:
                        continue
                    for line in file_lines:
                        for prefix in list(unconfirmed_prefixes):
                            # Check if this line mentions both the _type column and
                            # the target model class name
                            type_col = f"{prefix}_type"
                            if type_col in line and model_class in line:
                                evidence_prefixes.add(prefix)
                                unconfirmed_prefixes.discard(prefix)
                        if not unconfirmed_prefixes:
                            break
                    if not unconfirmed_prefixes:
                        break
                if not unconfirmed_prefixes:
                    break

        # Build results — only include pairs with evidence
        results = []
        for (child_table, prefix), (line_num, snippet) in poly_pairs.items():
            if prefix in confirmed_prefixes:
                results.append(ScanResult(
                    file_path="db/schema.rb",
                    line_number=line_num,
                    table_name=child_table,
                    column_name=f"{prefix}_id",
                    reference_type=ReferenceType.POLYMORPHIC_MODEL,
                    code_snippet=snippet,
                    confidence=Confidence.HIGH,
                ))
            elif prefix in evidence_prefixes:
                results.append(ScanResult(
                    file_path="db/schema.rb",
                    line_number=line_num,
                    table_name=child_table,
                    column_name=f"{prefix}_id",
                    reference_type=ReferenceType.POLYMORPHIC_SCHEMA,
                    code_snippet=snippet,
                    confidence=Confidence.MEDIUM,
                ))
            # No evidence — skip entirely

        return results
