"""Data structures for scan results."""

from dataclasses import dataclass
from enum import Enum


class Confidence(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    def __ge__(self, other):
        order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        return order[self] >= order[other]

    def __gt__(self, other):
        order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        return order[self] > order[other]

    def __le__(self, other):
        order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        return order[self] <= order[other]

    def __lt__(self, other):
        order = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}
        return order[self] < order[other]


class ReferenceType(Enum):
    SCHEMA_COLUMN = "schema_column"
    SCHEMA_REFERENCE = "schema_reference"
    MIGRATION_ADD_REFERENCE = "migration_add_reference"
    MIGRATION_ADD_COLUMN = "migration_add_column"
    MIGRATION_ADD_FOREIGN_KEY = "migration_add_foreign_key"
    MIGRATION_CREATE_TABLE_REF = "migration_create_table_ref"
    MIGRATION_REMOVE = "migration_remove"
    MODEL_BELONGS_TO = "model_belongs_to"
    MODEL_HAS_MANY = "model_has_many"
    MODEL_HAS_ONE = "model_has_one"
    MODEL_HAS_MANY_THROUGH = "model_has_many_through"
    MODEL_INDIRECT_ASSOCIATION = "model_indirect_association"
    # Reverse-direction associations: FK lives on the target table, not the owner
    MODEL_HAS_MANY_REVERSE = "model_has_many_reverse"
    MODEL_HAS_ONE_REVERSE = "model_has_one_reverse"
    RAW_SQL_COLUMN_REF = "raw_sql_column_ref"
    RAW_SQL_TABLE_REF = "raw_sql_table_ref"
    RAW_SQL_JOIN = "raw_sql_join"
    RAW_SQL_QUERY_METHOD = "raw_sql_query_method"
    RAW_SQL_INTERPOLATION = "raw_sql_interpolation"
    CONFIG_TABLE_REF = "config_table_ref"
    CONTEXTUAL_VARIABLE = "contextual_variable"
    CONTEXTUAL_COMMENT = "contextual_comment"
    POLYMORPHIC_SCHEMA = "polymorphic_schema"
    POLYMORPHIC_MODEL = "polymorphic_model"


class FileCategory(Enum):
    SCHEMA = "schema"
    MIGRATION = "migration"
    MODEL = "model"
    RUBY_OTHER = "ruby_other"
    SQL = "sql"
    ERB = "erb"
    YML = "yml"


@dataclass
class ScanResult:
    file_path: str
    line_number: int
    table_name: str
    column_name: str
    reference_type: ReferenceType
    code_snippet: str
    confidence: Confidence
    # Set to False when schema.rb validation finds the column does not exist in the table
    schema_verified: bool = True

    @property
    def dedup_key(self):
        return (self.file_path, self.line_number, self.reference_type)
