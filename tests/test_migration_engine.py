"""
Unit tests for the migration engine (mapper, validator).
No real DB needed.
"""

import pytest

from app.migration.mapper import apply_mappings, build_column_mappings
from app.migration.validator import SchemaCompatibilityError, validate_schema_compatibility
from app.schemas.migration import ColumnSchema, TableSchema


def _make_schema(name: str, cols: list[tuple]) -> TableSchema:
    """Helper: cols = [(name, type, nullable, is_pk)]"""
    columns = [
        ColumnSchema(name=c[0], data_type=c[1], is_nullable=c[2], is_primary_key=c[3])
        for c in cols
    ]
    pks = [c.name for c in columns if c.is_primary_key]
    return TableSchema(name=name, columns=columns, primary_keys=pks, row_count=0)


# ── Validator ─────────────────────────────────────────────────────────────────

def test_validate_empty_source_raises():
    src = TableSchema(name="t", columns=[], primary_keys=[], row_count=0)
    with pytest.raises(SchemaCompatibilityError):
        validate_schema_compatibility(src, None)


def test_validate_compatible_schemas():
    src = _make_schema("users", [("id", "INTEGER", False, True), ("name", "VARCHAR", True, False)])
    dst = _make_schema("users", [("id", "INTEGER", False, True), ("name", "VARCHAR", True, False)])
    warnings = validate_schema_compatibility(src, dst)
    assert warnings == []


def test_validate_incompatible_type_families_raises():
    src = _make_schema("t", [("col", "INTEGER", True, False)])
    dst = _make_schema("t", [("col", "DATE", True, False)])
    with pytest.raises(SchemaCompatibilityError, match="Incompatible type families"):
        validate_schema_compatibility(src, dst)


def test_validate_warns_on_missing_dest_column():
    src = _make_schema("t", [("a", "TEXT", True, False), ("b", "TEXT", True, False)])
    dst = _make_schema("t", [("a", "TEXT", True, False)])
    warnings = validate_schema_compatibility(src, dst)
    assert any("b" in w for w in warnings)


# ── Mapper ────────────────────────────────────────────────────────────────────

def test_build_mappings_all_included_when_no_dest():
    src = _make_schema("t", [("id", "INTEGER", False, True), ("name", "TEXT", True, False)])
    mappings = build_column_mappings(src, None)
    assert all(m["include"] for m in mappings)
    assert len(mappings) == 2


def test_build_mappings_excludes_missing_dest_col():
    src = _make_schema("t", [("id", "INTEGER", False, True), ("extra", "TEXT", True, False)])
    dst = _make_schema("t", [("id", "INTEGER", False, True)])
    mappings = build_column_mappings(src, dst)
    excluded = [m for m in mappings if not m["include"]]
    assert any(m["source_col"] == "extra" for m in excluded)


def test_apply_mappings_coerces_boolean():
    mappings = [{"source_col": "active", "dest_col": "active", "source_type": "INT", "dest_type": "BOOLEAN", "include": True}]
    rows = [{"active": 1}, {"active": 0}]
    result = apply_mappings(rows, mappings)
    assert result[0]["active"] is True
    assert result[1]["active"] is False


def test_apply_mappings_drops_excluded_columns():
    mappings = [
        {"source_col": "id", "dest_col": "id", "source_type": "INTEGER", "dest_type": "INTEGER", "include": True},
        {"source_col": "secret", "dest_col": "secret", "source_type": "TEXT", "dest_type": "TEXT", "include": False},
    ]
    rows = [{"id": 1, "secret": "hidden"}]
    result = apply_mappings(rows, mappings)
    assert "secret" not in result[0]
    assert result[0]["id"] == 1
