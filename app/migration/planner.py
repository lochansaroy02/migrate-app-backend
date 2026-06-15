"""
Reads source schema, compares it to the destination (if it exists),
and produces a MigrationPlan that the executor follows.
"""

from app.migration.mapper import build_column_mappings
from app.migration.validator import SchemaCompatibilityError, validate_schema_compatibility
from app.providers.base_provider import BaseDatabaseProvider
from app.schemas.migration import MigrationPlan, MigrationTablePlan, TableSchema
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MigrationPlanner:
    def __init__(
        self,
        source: BaseDatabaseProvider,
        destination: BaseDatabaseProvider,
        table_names: list[str],
    ) -> None:
        self._source = source
        self._destination = destination
        self._table_names = table_names

    async def build_plan(self) -> MigrationPlan:
        table_plans: list[MigrationTablePlan] = []
        total_rows = 0
        all_warnings: list[str] = []

        for table_name in self._table_names:
            logger.info("Planning table", table=table_name)

            try:
                src_schema: TableSchema = await self._source.get_table_schema(table_name)
            except Exception as exc:
                logger.error("Failed to read source schema", table=table_name, error=str(exc))
                all_warnings.append(f"Could not read schema for table '{table_name}': {exc}")
                continue

            dest_schema: TableSchema | None = None
            dest_exists = await self._destination.table_exists(table_name)
            if dest_exists:
                try:
                    dest_schema = await self._destination.get_table_schema(table_name)
                except Exception as exc:
                    logger.warning(
                        "Failed to read destination schema", table=table_name, error=str(exc)
                    )
                    all_warnings.append(
                        f"Could not read destination schema for '{table_name}': {exc}"
                    )

            try:
                warnings = validate_schema_compatibility(src_schema, dest_schema)
                all_warnings.extend(warnings)
            except SchemaCompatibilityError as exc:
                logger.error("Schema incompatible", table=table_name, error=str(exc))
                all_warnings.append(f"FATAL for table '{table_name}': {exc}")
                # Still include the table in the plan but mark it
                table_plans.append(
                    MigrationTablePlan(
                        table_name=table_name,
                        source_schema=src_schema,
                        destination_schema=dest_schema,
                        column_mappings=[],
                        row_count=src_schema.row_count,
                        status="skipped",
                    )
                )
                continue

            mappings = build_column_mappings(src_schema, dest_schema)
            total_rows += src_schema.row_count

            table_plans.append(
                MigrationTablePlan(
                    table_name=table_name,
                    source_schema=src_schema,
                    destination_schema=dest_schema,
                    column_mappings=mappings,
                    row_count=src_schema.row_count,
                    status="pending",
                )
            )

        return MigrationPlan(
            tables=table_plans,
            total_rows=total_rows,
            warnings=all_warnings,
        )
