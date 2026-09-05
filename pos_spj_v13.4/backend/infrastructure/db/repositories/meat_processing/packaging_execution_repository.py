"""PackagingExecutionRepository — persists PackagingExecution entities (§25)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.packaging_execution import PackagingExecution
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> PackagingExecution:
    return PackagingExecution(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], product_id=row["product_id"],
        packaging_material_id=row["packaging_material_id"],
        package_quantity=row["package_quantity"], net_weight=to_decimal(row["net_weight"]),
        gross_weight=to_decimal(row["gross_weight"]), tare_weight=to_decimal(row["tare_weight"]),
        packaged_by_user_id=row["packaged_by_user_id"], lot_id=row["lot_id"],
        process_output_id=row["process_output_id"],
        production_date=parse_dt(row["production_date"]),
        expiration_date=parse_dt(row["expiration_date"]),
        packaged_at=parse_dt(row["packaged_at"]))


class PackagingExecutionRepository(MeatProcessingRepositoryBase):
    def save(self, packaging: PackagingExecution) -> None:
        self._execute(
            "INSERT INTO packaging_executions (id, operation_id, processing_order_id,"
            " process_output_id, product_id, lot_id, packaging_material_id,"
            " package_quantity, net_weight, gross_weight, tare_weight, packaged_by_user_id,"
            " production_date, expiration_date, packaged_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (packaging.id, packaging.operation_id, packaging.processing_order_id,
             packaging.process_output_id, packaging.product_id, packaging.lot_id,
             packaging.packaging_material_id, packaging.package_quantity,
             dec_str(packaging.net_weight), dec_str(packaging.gross_weight),
             dec_str(packaging.tare_weight), packaging.packaged_by_user_id,
             dt_str(packaging.production_date), dt_str(packaging.expiration_date),
             dt_str(packaging.packaged_at)))

    def get(self, packaging_id: str) -> PackagingExecution | None:
        row = self._query_one(
            "SELECT * FROM packaging_executions WHERE id=?", (packaging_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[PackagingExecution]:
        rows = self._query(
            "SELECT * FROM packaging_executions WHERE processing_order_id=?"
            " ORDER BY packaged_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]
