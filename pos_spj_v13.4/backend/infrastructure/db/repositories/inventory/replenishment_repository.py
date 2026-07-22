"""Replenishment repositories (§34, INV-18).

RuleRepository upserts the min/max/safety/target policy (one per product/branch/
warehouse); SuggestionRepository persists the evaluated output. Neither touches
stock — that is the ledger's job.
"""

from __future__ import annotations

from backend.domain.inventory.entities.replenishment import (
    ReplenishmentRule,
    ReplenishmentSuggestion,
)
from backend.domain.inventory.enums import (
    ReplenishmentBasis,
    ReplenishmentSource,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    opt_dec_str,
    to_decimal,
)


def rule_from_row(row: dict) -> ReplenishmentRule:
    return ReplenishmentRule(
        id=row["id"], product_id=row["product_id"], branch_id=row["branch_id"],
        warehouse_id=row["warehouse_id"], basis=ReplenishmentBasis(row["basis"]),
        min_quantity=to_decimal(row["min_quantity"]),
        reorder_point=to_decimal(row["reorder_point"]),
        target_quantity=to_decimal(row["target_quantity"]),
        max_quantity=(None if row["max_quantity"] is None
                      else to_decimal(row["max_quantity"])),
        safety_stock=to_decimal(row["safety_stock"]),
        lead_time_days=row["lead_time_days"],
        preferred_source=ReplenishmentSource(row["preferred_source"]),
        source_warehouse_id=row["source_warehouse_id"],
        active=bool(row["active"]), created_at=row["created_at"])


class ReplenishmentRuleRepository(InventoryRepositoryBase):
    def upsert(self, rule: ReplenishmentRule) -> None:
        self._execute(
            "INSERT INTO inventory_replenishment_rule (id, product_id, branch_id,"
            " warehouse_id, basis, min_quantity, reorder_point, target_quantity,"
            " max_quantity, safety_stock, lead_time_days, preferred_source,"
            " source_warehouse_id, active, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(product_id, branch_id, warehouse_id) DO UPDATE SET"
            " basis=excluded.basis, min_quantity=excluded.min_quantity,"
            " reorder_point=excluded.reorder_point,"
            " target_quantity=excluded.target_quantity,"
            " max_quantity=excluded.max_quantity, safety_stock=excluded.safety_stock,"
            " lead_time_days=excluded.lead_time_days,"
            " preferred_source=excluded.preferred_source,"
            " source_warehouse_id=excluded.source_warehouse_id, active=excluded.active",
            (rule.id, rule.product_id, rule.branch_id, rule.warehouse_id,
             enum_value(rule.basis), dec_str(rule.min_quantity),
             dec_str(rule.reorder_point), dec_str(rule.target_quantity),
             opt_dec_str(rule.max_quantity), dec_str(rule.safety_stock),
             rule.lead_time_days, enum_value(rule.preferred_source),
             rule.source_warehouse_id, 1 if rule.active else 0, rule.created_at))

    def get(self, *, product_id: str, branch_id: str, warehouse_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM inventory_replenishment_rule WHERE product_id=?"
            " AND branch_id=? AND warehouse_id=?",
            (product_id, branch_id, warehouse_id))

    def list_active(self, *, branch_id: str | None = None) -> list[dict]:
        if branch_id:
            return self._query(
                "SELECT * FROM inventory_replenishment_rule WHERE active=1"
                " AND branch_id=? ORDER BY product_id", (branch_id,))
        return self._query(
            "SELECT * FROM inventory_replenishment_rule WHERE active=1"
            " ORDER BY branch_id, product_id")


class ReplenishmentSuggestionRepository(InventoryRepositoryBase):
    def save(self, s: ReplenishmentSuggestion) -> None:
        self._execute(
            "INSERT INTO inventory_replenishment_suggestion (id, rule_id, product_id,"
            " branch_id, warehouse_id, basis, current_available, suggested_quantity,"
            " source_type, source_warehouse_id, urgency, status, operation_id,"
            " generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.rule_id, s.product_id, s.branch_id, s.warehouse_id,
             enum_value(s.basis), dec_str(s.current_available),
             dec_str(s.suggested_quantity), enum_value(s.source_type),
             s.source_warehouse_id, enum_value(s.urgency), enum_value(s.status),
             s.operation_id, s.generated_at))

    def list_open(self, *, branch_id: str | None = None) -> list[dict]:
        if branch_id:
            return self._query(
                "SELECT * FROM inventory_replenishment_suggestion WHERE status='OPEN'"
                " AND branch_id=? ORDER BY generated_at DESC", (branch_id,))
        return self._query(
            "SELECT * FROM inventory_replenishment_suggestion WHERE status='OPEN'"
            " ORDER BY generated_at DESC")

    def exists_for_operation(self, operation_id: str) -> bool:
        return self._query_one(
            "SELECT id FROM inventory_replenishment_suggestion WHERE operation_id=?"
            " LIMIT 1", (operation_id,)) is not None

    def set_status(self, suggestion_id: str, status: str) -> None:
        self._execute(
            "UPDATE inventory_replenishment_suggestion SET status=? WHERE id=?",
            (status, suggestion_id))
