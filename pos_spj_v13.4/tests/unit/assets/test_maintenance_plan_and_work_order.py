"""ASSET-6 — MaintenancePlan and MaintenanceWorkOrder (§23-25).

`complete()` records `actual_cost` as evidence only; it must never post to
Finance/Treasury from the entity itself (docs/refactor/assets_finance_boundary_map.md).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.assets.entities.maintenance_plan import MaintenancePlan
from backend.domain.assets.entities.maintenance_work_order import MaintenanceWorkOrder
from backend.domain.assets.enums import (
    MaintenanceFrequencyType,
    MaintenancePlanStatus,
    MaintenanceProviderType,
    MaintenanceType,
    MaintenanceWorkOrderStatus,
)
from backend.domain.assets.exceptions import AssetDomainError, MaintenanceStateInvalidError
from backend.domain.finance.value_objects.money import Money


def _money(v: str) -> Money:
    return Money(Decimal(v))


class TestMaintenancePlan:
    def test_create_monthly_plan(self):
        plan = MaintenancePlan.create("asset-1", MaintenanceType.PREVENTIVE,
                                      MaintenanceFrequencyType.MONTHLY, "op-1",
                                      next_due_at=date(2026, 10, 1))
        assert plan.status is MaintenancePlanStatus.ACTIVE
        assert plan.next_due_at == date(2026, 10, 1)

    def test_custom_frequency_requires_value(self):
        with pytest.raises(AssetDomainError):
            MaintenancePlan.create("asset-1", MaintenanceType.PREVENTIVE,
                                   MaintenanceFrequencyType.CUSTOM, "op-1")

    def test_meter_based_requires_trigger(self):
        with pytest.raises(AssetDomainError):
            MaintenancePlan.create("asset-1", MaintenanceType.PREVENTIVE,
                                   MaintenanceFrequencyType.METER_BASED, "op-1")

    def test_pause_resume_deactivate(self):
        plan = MaintenancePlan.create("asset-1", MaintenanceType.PREVENTIVE,
                                      MaintenanceFrequencyType.QUARTERLY, "op-1")
        plan.pause()
        assert plan.status is MaintenancePlanStatus.PAUSED
        plan.resume()
        assert plan.status is MaintenancePlanStatus.ACTIVE
        plan.deactivate()
        assert plan.status is MaintenancePlanStatus.INACTIVE

    def test_reschedule_paused_plan_fails(self):
        plan = MaintenancePlan.create("asset-1", MaintenanceType.PREVENTIVE,
                                      MaintenanceFrequencyType.MONTHLY, "op-1")
        plan.pause()
        with pytest.raises(MaintenanceStateInvalidError):
            plan.reschedule(date(2026, 12, 1))


def _wo(**extra) -> MaintenanceWorkOrder:
    return MaintenanceWorkOrder.create("WO-000001", "asset-1", MaintenanceType.CORRECTIVE,
                                       "op-1", created_by_user_id="u1", **extra)


class TestMaintenanceWorkOrderLifecycle:
    def test_full_internal_lifecycle(self):
        wo = _wo()
        wo.submit()
        assert wo.status is MaintenanceWorkOrderStatus.REQUESTED
        wo.approve("approver-1")
        assert wo.status is MaintenanceWorkOrderStatus.APPROVED
        wo.schedule("2026-09-10T10:00:00")
        assert wo.status is MaintenanceWorkOrderStatus.SCHEDULED
        wo.assign(employee_id="tech-1")
        assert wo.status is MaintenanceWorkOrderStatus.ASSIGNED
        assert wo.provider_type is MaintenanceProviderType.INTERNAL
        wo.start()
        assert wo.status is MaintenanceWorkOrderStatus.IN_PROGRESS
        assert wo.started_at is not None
        wo.complete(_money("450.00"), "Compresor reemplazado", downtime_minutes=120)
        assert wo.status is MaintenanceWorkOrderStatus.COMPLETED
        assert wo.actual_cost.amount == Decimal("450.00")
        wo.close()
        assert wo.status is MaintenanceWorkOrderStatus.CLOSED

    def test_assign_external_supplier_sets_provider_type(self):
        wo = _wo()
        wo.submit()
        wo.approve("approver-1")
        wo.schedule("2026-09-10T10:00:00")
        wo.assign(supplier_id="sup-1")
        assert wo.provider_type is MaintenanceProviderType.EXTERNAL

    def test_pause_and_resume(self):
        wo = _wo()
        wo.submit()
        wo.approve("a1")
        wo.schedule("2026-09-10")
        wo.assign(employee_id="tech-1")
        wo.start()
        wo.pause()
        assert wo.status is MaintenanceWorkOrderStatus.PAUSED
        wo.start()
        assert wo.status is MaintenanceWorkOrderStatus.IN_PROGRESS

    def test_wait_for_parts_and_resume(self):
        wo = _wo()
        wo.submit()
        wo.approve("a1")
        wo.schedule("2026-09-10")
        wo.assign(employee_id="tech-1")
        wo.start()
        wo.wait_for_parts()
        assert wo.status is MaintenanceWorkOrderStatus.WAITING_PARTS
        wo.resume_from_wait()
        assert wo.status is MaintenanceWorkOrderStatus.IN_PROGRESS

    def test_complete_requires_resolution(self):
        wo = _wo()
        wo.submit()
        wo.approve("a1")
        wo.schedule("2026-09-10")
        wo.assign(employee_id="tech-1")
        wo.start()
        with pytest.raises(AssetDomainError):
            wo.complete(_money("10"), "")

    def test_complete_from_draft_fails(self):
        wo = _wo()
        with pytest.raises(MaintenanceStateInvalidError):
            wo.complete(_money("10"), "resolved")

    def test_cancel_from_draft(self):
        wo = _wo()
        wo.cancel("duplicate")
        assert wo.status is MaintenanceWorkOrderStatus.CANCELLED

    def test_cancel_terminal_fails(self):
        wo = _wo()
        wo.cancel()
        with pytest.raises(MaintenanceStateInvalidError):
            wo.cancel()

    def test_version_increments_on_transition(self):
        wo = _wo()
        assert wo.version == 1
        wo.submit()
        assert wo.version == 2

    def test_complete_never_touches_finance_or_treasury(self):
        """Guardrail-adjacent unit check: MaintenanceWorkOrder has no attribute
        or method referencing finance/treasury posting — completion only
        records evidence (actual_cost/resolution), the application layer emits
        MAINTENANCE_COST_CONFIRMED separately."""
        wo = _wo()
        for name in dir(wo):
            assert "asiento" not in name.lower()
            assert "treasury" not in name.lower()
            assert "posting" not in name.lower()
