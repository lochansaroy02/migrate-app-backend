"""
Validates that two schemas are compatible before a migration starts.
Returns a list of warnings (non-fatal) and raises MigrationError for fatal issues.
"""

from app.schemas.migration import ColumnSchema, TableSchema
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SchemaCompatibilityError(Exception):
    pass


_NUMERIC_TYPES = {"INTEGER", "SMALLINT", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"}
_STRING_TYPES = {"CHAR", "VARCHAR", "TEXT", "NCHAR", "NVARCHAR", "NTEXT"}
_DATE_TYPES = {"DATE", "TIME", "DATETIME", "TIMESTAMP", "TIMETZ", "TIMESTAMPTZ"}
_BOOLEAN_TYPES = {"BOOLEAN", "BOOL", "BIT"}
_BINARY_TYPES = {"BLOB", "BYTEA", "BINARY", "VARBINARY"}
_JSON_TYPES = {"JSON", "JSONB"}

_TYPE_FAMILIES: list[set[str]] = [
    _NUMERIC_TYPES,
    _STRING_TYPES,
    _DATE_TYPES,
    _BOOLEAN_TYPES,
    _BINARY_TYPES,
    _JSON_TYPES,
]


def _family(dtype: str) -> int:
    """Return the family index of *dtype*, or -1 if unknown."""
    upper = dtype.upper().split("(")[0]
    for i, fam in enumerate(_TYPE_FAMILIES):
        if upper in fam:
            return i
    return -1


def validate_schema_compatibility(
    source: TableSchema,
    destination: TableSchema | None,
) -> list[str]:
    """
    Check that *source* can be migrated.
    If *destination* already exists, also cross-check column types.
    Returns a list of warning strings (empty = fully compatible).
    Raises SchemaCompatibilityError for unrecoverable issues.
    """
    warnings: list[str] = []

    if not source.columns:
        raise SchemaCompatibilityError(
            f"Table '{source.name}' has no columns — cannot migrate."
        )

    if destination is None:
        return warnings  # destination will be created from source

    # Build lookup for fast access
    dest_cols: dict[str, ColumnSchema] = {c.name: c for c in destination.columns}
    src_cols: dict[str, ColumnSchema] = {c.name: c for c in source.columns}

    for col in source.columns:
        if col.name not in dest_cols:
            warnings.append(
                f"Column '{col.name}' in source table '{source.name}' "
                f"does not exist in destination — it will be skipped."
            )
            continue

        dcol = dest_cols[col.name]
        src_fam = _family(col.data_type)
        dst_fam = _family(dcol.data_type)

        if src_fam != -1 and dst_fam != -1 and src_fam != dst_fam:
            raise SchemaCompatibilityError(
                f"Incompatible type families for column '{col.name}' in table "
                f"'{source.name}': source={col.data_type}, destination={dcol.data_type}."
            )

        if dcol.max_length and col.max_length and col.max_length > dcol.max_length:
            warnings.append(
                f"Column '{col.name}': source max_length ({col.max_length}) "
                f"exceeds destination ({dcol.max_length}) — data may be truncated."
            )

        if not col.is_nullable and dcol.is_nullable is False and col.is_primary_key is False:
            # Source is NOT NULL but destination column is NOT NULL and has no default
            pass  # acceptable, migration will carry values

    for dest_col_name in dest_cols:
        if dest_col_name not in src_cols:
            dcol = dest_cols[dest_col_name]
            if not dcol.is_nullable and dcol.default is None:
                raise SchemaCompatibilityError(
                    f"Destination column '{dest_col_name}' in table '{destination.name}' "
                    f"is NOT NULL with no default but has no matching source column."
                )
            warnings.append(
                f"Column '{dest_col_name}' in destination table '{destination.name}' "
                f"has no matching source column — it will receive NULL / default values."
            )

    return warnings
