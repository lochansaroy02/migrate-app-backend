"""
Maps source columns to destination columns and transforms row values.
The default implementation is a simple name-match with type coercion.
Future versions can add explicit rename maps or value transformations.
"""

from typing import Any

from app.core.constants import TYPE_AFFINITY
from app.schemas.migration import ColumnSchema, TableSchema


def _universal_type(dtype: str) -> str:
    lower = dtype.lower().split("(")[0].strip()
    return TYPE_AFFINITY.get(lower, dtype.upper())


def build_column_mappings(
    source: TableSchema,
    destination: TableSchema | None,
) -> list[dict]:
    """
    Return a list of column mapping descriptors:
      {
        "source_col": str,
        "dest_col": str,
        "source_type": str,
        "dest_type": str,
        "include": bool,   # False = column skipped
      }
    """
    mappings = []
    dest_cols: dict[str, ColumnSchema] = (
        {c.name: c for c in destination.columns} if destination else {}
    )

    for col in source.columns:
        dest_col = dest_cols.get(col.name)
        include = dest_col is not None if destination else True
        mappings.append(
            {
                "source_col": col.name,
                "dest_col": col.name,
                "source_type": col.data_type,
                "dest_type": dest_col.data_type if dest_col else col.data_type,
                "include": include,
            }
        )

    return mappings


def apply_mappings(
    rows: list[dict[str, Any]],
    mappings: list[dict],
) -> list[dict[str, Any]]:
    """
    Transform a batch of source rows into destination rows using *mappings*.
    Excluded columns are dropped; values are lightly coerced where possible.
    """
    active = [m for m in mappings if m["include"]]
    result = []
    for row in rows:
        new_row = {}
        for m in active:
            value = row.get(m["source_col"])
            new_row[m["dest_col"]] = _coerce(value, m["dest_type"])
        result.append(new_row)
    return result


def _coerce(value: Any, dest_type: str) -> Any:
    """Best-effort type coercion for cross-database migrations."""
    if value is None:
        return None

    upper = dest_type.upper().split("(")[0]

    # Booleans often come as 0/1 from MySQL
    if upper == "BOOLEAN":
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "t")
        return value

    # Ensure numeric strings don't break integer columns
    if upper in ("INTEGER", "SMALLINT", "BIGINT") and isinstance(value, float):
        return int(value)

    # JSON-like objects can be serialised to string if needed
    if upper in ("TEXT", "VARCHAR", "CHAR") and isinstance(value, (dict, list)):
        import json
        return json.dumps(value, default=str)

    return value
