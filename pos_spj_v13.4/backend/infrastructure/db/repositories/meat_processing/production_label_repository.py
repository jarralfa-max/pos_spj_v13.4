"""ProductionLabelRepository — persists ProductionLabel entities (§25)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.production_label import ProductionLabel
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    parse_dt,
)


def _to_entity(row: dict) -> ProductionLabel:
    return ProductionLabel(
        id=row["id"], operation_id=row["operation_id"],
        packaging_execution_id=row["packaging_execution_id"],
        label_template_id=row["label_template_id"], barcode=row["barcode"],
        qr_traceability_reference=row["qr_traceability_reference"],
        printed_at=parse_dt(row["printed_at"]), printed_by_user_id=row["printed_by_user_id"],
        reprint_count=row["reprint_count"], created_at=parse_dt(row["created_at"]))


class ProductionLabelRepository(MeatProcessingRepositoryBase):
    def save(self, label: ProductionLabel) -> None:
        self._execute(
            "INSERT INTO production_labels (id, operation_id, packaging_execution_id,"
            " label_template_id, barcode, qr_traceability_reference, printed_at,"
            " printed_by_user_id, reprint_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET printed_at=excluded.printed_at,"
            " printed_by_user_id=excluded.printed_by_user_id,"
            " reprint_count=excluded.reprint_count",
            (label.id, label.operation_id, label.packaging_execution_id,
             label.label_template_id, label.barcode, label.qr_traceability_reference,
             dt_str(label.printed_at), label.printed_by_user_id, label.reprint_count,
             dt_str(label.created_at)))

    def get(self, label_id: str) -> ProductionLabel | None:
        row = self._query_one("SELECT * FROM production_labels WHERE id=?", (label_id,))
        return None if row is None else _to_entity(row)

    def list_by_packaging(self, packaging_execution_id: str) -> list[ProductionLabel]:
        rows = self._query(
            "SELECT * FROM production_labels WHERE packaging_execution_id=?"
            " ORDER BY created_at", (packaging_execution_id,))
        return [_to_entity(row) for row in rows]
