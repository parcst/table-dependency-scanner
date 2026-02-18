"""Scanner registry."""

from .schema_scanner import SchemaScanner
from .migration_scanner import MigrationScanner
from .model_scanner import ModelScanner
from .raw_sql_scanner import RawSqlScanner
from .config_scanner import ConfigScanner
from .contextual_scanner import ContextualScanner
from .polymorphic_scanner import PolymorphicScanner

ALL_SCANNERS = [
    SchemaScanner,
    MigrationScanner,
    ModelScanner,
    RawSqlScanner,
    ConfigScanner,
    ContextualScanner,
    PolymorphicScanner,
]
