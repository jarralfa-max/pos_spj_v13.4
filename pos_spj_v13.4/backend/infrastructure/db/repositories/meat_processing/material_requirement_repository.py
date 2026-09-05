"""MaterialRequirementRepository — persists MaterialRequirement entities (§16)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.material_requirement import MaterialRequirement
from backend.domain.meat_processing.enums import MaterialRequirementStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    bool_int,
    dec_str,
    dt_str,
    enum_value,
    int_bool,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> MaterialRequirement:
    return MaterialRequirement(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], product_id=row["product_id"],
        required_quantity=to_decimal(row["required_quantity"]),
        required_weight=to_decimal(row["required_weight"]), unit=row["unit"],
        substitution_allowed=int_bool(row["substitution_allowed"]),
        quality_required=int_bool(row["quality_required"]),
        lot_required=int_bool(row["lot_required"]),
        status=MaterialRequirementStatus(row["status"]),
        reserved_quantity=to_decimal(row["reserved_quantity"]),
        reserved_weight=to_decimal(row["reserved_weight"]),
        allocated_quantity=to_decimal(row["allocated_quantity"]),
        allocated_weight=to_decimal(row["allocated_weight"]),
        consumed_quantity=to_decimal(row["consumed_quantity"]),
        consumed_weight=to_decimal(row["consumed_weight"]),
        created_at=parse_dt(row["created_at"]))


class MaterialRequirementRepository(MeatProcessingRepositoryBase):
    def save(self, requirement: MaterialRequirement) -> None:
        self._execute(
            "INSERT INTO material_requirements (id, operation_id, processing_order_id,"
            " product_id, required_quantity, required_weight, unit, substitution_allowed,"
            " quality_required, lot_required, status, reserved_quantity, reserved_weight,"
            " allocated_quantity, allocated_weight, consumed_quantity, consumed_weight,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " reserved_quantity=excluded.reserved_quantity,"
            " reserved_weight=excluded.reserved_weight,"
            " allocated_quantity=excluded.allocated_quantity,"
            " allocated_weight=excluded.allocated_weight,"
            " consumed_quantity=excluded.consumed_quantity,"
            " consumed_weight=excluded.consumed_weight",
            (requirement.id, requirement.operation_id, requirement.processing_order_id,
             requirement.product_id, dec_str(requirement.required_quantity),
             dec_str(requirement.required_weight), requirement.unit,
             bool_int(requirement.substitution_allowed), bool_int(requirement.quality_required),
             bool_int(requirement.lot_required), enum_value(requirement.status),
             dec_str(requirement.reserved_quantity), dec_str(requirement.reserved_weight),
             dec_str(requirement.allocated_quantity), dec_str(requirement.allocated_weight),
             dec_str(requirement.consumed_quantity), dec_str(requirement.consumed_weight),
             dt_str(requirement.created_at)))

    def get(self, requirement_id: str) -> MaterialRequirement | None:
        row = self._query_one(
            "SELECT * FROM material_requirements WHERE id=?", (requirement_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[MaterialRequirement]:
        rows = self._query(
            "SELECT * FROM material_requirements WHERE processing_order_id=?"
            " ORDER BY created_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]
