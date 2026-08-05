from datetime import date
from decimal import Decimal

import pytest

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.expiry_damage import (
    AssessLotRiskCommand,
    BlockAtRiskLotCommand,
    ExpiryDamageWorkflowService,
)
from backend.domain.losses.expiry_damage import DamageSeverity, ExpiryDamageRiskPolicy, LotRiskLevel
from backend.domain.losses.exceptions import LossInvariantError


class AllowAuthorization:
    def __init__(self):
        self.required = []

    def require(self, actor, permission):
        self.required.append((actor, permission))


class MemoryRepository:
    def __init__(self):
        self.processed = {}
        self.case = {
            "id": "case", "branch_id": "branch", "warehouse_id": "warehouse",
            "status": "SUBMITTED", "product_id": "product", "lot_id": "lot",
            "quantity": Decimal("4"), "weight": Decimal("12.5"),
            "expiration_date": "2026-08-05", "quarantine_id": None,
        }

    class Tx:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    def transaction(self): return self.Tx()
    def find_processed(self, op): return self.processed.get(op)
    def get_lot_case(self, case_id, lot_id):
        return self.case if (case_id, lot_id) == ("case", "lot") else None
    def record_assessment(self, *, operation_id, assessment, case, actor_user_id):
        self.processed[operation_id] = {"kind": "ASSESS", "entity_id": case["id"],
                                        "risk_level": assessment.risk_level.value}
    def record_block(self, *, operation_id, case, quarantine_id, assessment, actor_user_id):
        self.case["quarantine_id"] = quarantine_id
        self.case["status"] = "TREATMENT_PENDING"
        self.processed[operation_id] = {"kind": "BLOCK", "entity_id": case["id"],
                                        "quarantine_id": quarantine_id,
                                        "risk_level": assessment.risk_level.value}


class InventoryGateway:
    def __init__(self): self.calls = []
    def quarantine(self, **kw):
        self.calls.append(("quarantine", kw)); return type("R", (), {"success": True, "entity_id": "q1", "message": "ok"})()
    def release_quarantine(self, **kw):
        self.calls.append(("release", kw)); return type("R", (), {"success": True, "entity_id": kw["quarantine_id"], "message": "ok"})()


def context(actor="actor"):
    return LossExecutionContext(actor, "branch", frozenset(), frozenset({"warehouse"}))


def service():
    repo, inventory = MemoryRepository(), InventoryGateway()
    return ExpiryDamageWorkflowService(repo, inventory, AllowAuthorization()), repo, inventory


def test_policy_combines_expiry_and_damage_without_float_arithmetic():
    policy = ExpiryDamageRiskPolicy()
    result = policy.assess(expiration_date="2026-08-10", as_of=date(2026, 8, 3),
                           warning_days=10, critical_days=2,
                           damage_severity=DamageSeverity.MAJOR,
                           quantity=Decimal("2"), weight=Decimal("1.25"))
    assert result.risk_level is LotRiskLevel.HIGH
    assert result.days_to_expiry == 7
    with pytest.raises(LossInvariantError):
        policy.assess(expiration_date=None, damage_severity=DamageSeverity.MINOR,
                      quantity=1.5, weight=0)


def test_assess_and_block_are_idempotent_and_block_uses_inventory_quarantine():
    svc, repo, inventory = service()
    assessed = svc.assess(AssessLotRiskCommand("op-assess", "case", "lot", context(),
                                               date(2026, 8, 3), 7, 2,
                                               DamageSeverity.NONE))
    assert assessed.risk_level is LotRiskLevel.CRITICAL
    blocked = svc.block(BlockAtRiskLotCommand("op-block", "case", "lot", context(),
                                              date(2026, 8, 3), 7, 2,
                                              DamageSeverity.NONE, "Caducidad próxima"))
    replay = svc.block(BlockAtRiskLotCommand("op-block", "case", "lot", context(),
                                             date(2026, 8, 3), 7, 2,
                                             DamageSeverity.NONE, "Caducidad próxima"))
    assert blocked.quarantine_id == "q1" and replay.replayed
    assert len(inventory.calls) == 1
    assert inventory.calls[0][1]["owns_transaction"] is False

