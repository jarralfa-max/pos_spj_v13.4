"""Customer — the Customer Master aggregate root (§12).

Status/lifecycle-stage are two independent axes (master prompt §12): `status`
is the operational state this entity's methods govern (ACTIVE/SUSPENDED/
BLOCKED/CLOSED/...); `lifecycle_stage` is a CRM-relationship projection
(PROSPECT→LEAD→QUALIFIED→CUSTOMER→...) that CRM-4+ (Leads) mostly drives —
Customer only exposes a setter for it here, no transition rules.

`deactivate()` (→ INACTIVE, reversible) is not in the master prompt's use
case list (§58 only names Activate/Suspend/Block/Close) but is required by
CLAUDE.md Prioridad 0: it is the exact operation
`ModuloClientes.eliminar_cliente()` already performs today (soft-delete,
preserves history, reversible) — see
docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md §1. Dropping it would lose
existing functionality, which CLAUDE.md forbids regardless of what the
master prompt's use-case list enumerates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import CustomerStatus, CustomerType, LifecycleStage
from backend.domain.customers.exceptions import InvalidCustomerStateError
from backend.domain.customers.value_objects.customer_code import CustomerCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_REACTIVATABLE = {
    CustomerStatus.PROSPECT, CustomerStatus.INACTIVE,
    CustomerStatus.SUSPENDED, CustomerStatus.BLOCKED,
}
_BLOCKABLE = {CustomerStatus.ACTIVE, CustomerStatus.SUSPENDED, CustomerStatus.INACTIVE}
_CLOSABLE = {
    CustomerStatus.ACTIVE, CustomerStatus.INACTIVE,
    CustomerStatus.SUSPENDED, CustomerStatus.BLOCKED,
}
_TERMINAL = {CustomerStatus.CLOSED, CustomerStatus.MERGED, CustomerStatus.ANONYMIZED}


@dataclass(slots=True)
class Customer:
    id: str
    code: CustomerCode
    customer_type: CustomerType
    display_name: str
    legal_name: str = ""
    first_name: str = ""
    last_name: str = ""
    second_last_name: str = ""
    commercial_name: str = ""
    status: CustomerStatus = CustomerStatus.ACTIVE
    lifecycle_stage: LifecycleStage = LifecycleStage.CUSTOMER
    source: str = ""
    origin_branch_id: str | None = None
    primary_contact_id: str | None = None
    default_billing_address_id: str | None = None
    default_delivery_address_id: str | None = None
    account_owner_user_id: str | None = None
    territory_id: str | None = None
    created_by_user_id: str | None = None
    operation_id: str | None = None
    version: int = 1
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    activated_at: str | None = None
    suspended_at: str | None = None
    blocked_at: str | None = None
    closed_at: str | None = None
    # CRM-13 (§49 Ventas): sale-activity projection, updated by
    # RecordCustomerSaleActivityUseCase in reaction to Ventas'
    # SALE_COMPLETED/SALE_CANCELLED events — never written by Ventas
    # directly (CRM does not register sales, per §49).
    last_purchase_at: str | None = None
    purchase_count: int = 0
    # CRM-21 (migración de consumidores): bridges this aggregate to the
    # legacy ``clientes.id`` row it was backfilled/resolved from, when
    # applicable. None for customers created natively in this bounded
    # context (e.g. CRM-18's Alta rápida). See
    # backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py.
    legacy_customer_id: str | None = None

    # construction --------------------------------------------------------
    @classmethod
    def create(
        cls, code: CustomerCode, display_name: str, customer_type: CustomerType, *,
        legal_name: str = "", first_name: str = "", last_name: str = "",
        second_last_name: str = "", commercial_name: str = "", source: str = "",
        origin_branch_id: str | None = None, account_owner_user_id: str | None = None,
        territory_id: str | None = None, created_by_user_id: str | None = None,
        operation_id: str | None = None, as_prospect: bool = False,
        legacy_customer_id: str | None = None,
    ) -> "Customer":
        if not display_name or not display_name.strip():
            raise InvalidCustomerStateError("display_name es obligatorio")
        return cls(
            id=new_uuid(), code=code, customer_type=customer_type,
            display_name=display_name.strip(), legal_name=legal_name.strip(),
            first_name=first_name.strip(), last_name=last_name.strip(),
            second_last_name=second_last_name.strip(),
            commercial_name=commercial_name.strip(), source=source,
            origin_branch_id=origin_branch_id, account_owner_user_id=account_owner_user_id,
            territory_id=territory_id, created_by_user_id=created_by_user_id,
            operation_id=operation_id,
            status=CustomerStatus.PROSPECT if as_prospect else CustomerStatus.ACTIVE,
            lifecycle_stage=LifecycleStage.PROSPECT if as_prospect else LifecycleStage.CUSTOMER,
            legacy_customer_id=legacy_customer_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()
        self.version += 1

    # lifecycle -------------------------------------------------------------
    def activate(self) -> None:
        if self.status not in _REACTIVATABLE:
            raise InvalidCustomerStateError(
                f"No se puede activar desde {self.status.value}")
        self.status = CustomerStatus.ACTIVE
        self.activated_at = _utcnow()
        self._touch()

    def deactivate(self, reason: str = "") -> None:
        """Soft-delete: reversible, preserves history (see module docstring)."""
        if self.status is not CustomerStatus.ACTIVE:
            raise InvalidCustomerStateError("Solo se desactiva un cliente activo")
        self.status = CustomerStatus.INACTIVE
        self._touch()

    def suspend(self, reason: str) -> None:
        if self.status is not CustomerStatus.ACTIVE:
            raise InvalidCustomerStateError("Solo se suspende un cliente activo")
        if not reason.strip():
            raise InvalidCustomerStateError("La suspensión requiere un motivo")
        self.status = CustomerStatus.SUSPENDED
        self.suspended_at = _utcnow()
        self._touch()

    def block(self, reason: str) -> None:
        if self.status not in _BLOCKABLE:
            raise InvalidCustomerStateError(
                f"No se puede bloquear desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerStateError("El bloqueo requiere un motivo")
        self.status = CustomerStatus.BLOCKED
        self.blocked_at = _utcnow()
        self._touch()

    def close(self, reason: str) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidCustomerStateError(
                f"No se puede cerrar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerStateError("El cierre requiere un motivo")
        self.status = CustomerStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def mark_merged(self, into_customer_id: str) -> None:
        """Set by the CRM-11 merge use case once the merge is confirmed —
        this entity does not implement merge logic itself."""
        if not into_customer_id:
            raise InvalidCustomerStateError("mark_merged requiere el customer_id maestro")
        self.status = CustomerStatus.MERGED
        self._touch()

    def mark_anonymized(self) -> None:
        """Set by the CRM-9 privacy use case once anonymization is applied —
        this entity does not implement anonymization logic itself."""
        self.status = CustomerStatus.ANONYMIZED
        self._touch()

    # projections used elsewhere without a transition ------------------------
    def record_edit(self) -> None:
        """Bump updated_at/version for a plain field edit (no status change).
        Called by UpdateCustomerUseCase after it applies the requested field
        changes directly on this aggregate."""
        self._touch()

    def set_lifecycle_stage(self, stage: LifecycleStage) -> None:
        self.lifecycle_stage = stage
        self._touch()

    def assign_owner(self, user_id: str | None) -> None:
        self.account_owner_user_id = user_id
        self._touch()

    def assign_territory(self, territory_id: str | None) -> None:
        self.territory_id = territory_id
        self._touch()

    # sale-activity projection (CRM-13, §49) -----------------------------------
    def record_sale_activity(self, occurred_at: str) -> LifecycleStage | None:
        """React to a completed sale (Ventas' SALE_COMPLETED). Bumps the
        purchase counter/last-purchase timestamp and, only for a prospect/
        lead/qualified/lost/inactive relationship, advances lifecycle_stage
        to reflect a real purchase happened — never overrides an already
        active CUSTOMER/REPEAT_CUSTOMER/AT_RISK stage with a lesser one, and
        never moves it backwards. Returns the new stage if it changed, else
        None (so the caller only emits a LIFECYCLE_STAGE_CHANGED event when
        something actually moved)."""
        self.purchase_count += 1
        self.last_purchase_at = occurred_at
        previous = self.lifecycle_stage
        if previous in (LifecycleStage.PROSPECT, LifecycleStage.LEAD,
                        LifecycleStage.QUALIFIED, LifecycleStage.LOST):
            self.lifecycle_stage = LifecycleStage.CUSTOMER
        elif previous in (LifecycleStage.INACTIVE, LifecycleStage.AT_RISK):
            self.lifecycle_stage = LifecycleStage.REPEAT_CUSTOMER
        elif previous is LifecycleStage.CUSTOMER and self.purchase_count > 1:
            self.lifecycle_stage = LifecycleStage.REPEAT_CUSTOMER
        self._touch()
        return self.lifecycle_stage if self.lifecycle_stage is not previous else None

    def record_sale_cancelled(self) -> None:
        """React to a cancelled sale (Ventas' SALE_CANCELLED) — a completed
        sale that gets voided did not really happen, so it is un-counted.
        Deliberately does NOT try to recompute last_purchase_at from
        history (this bounded context does not own sales history, see
        CustomerHistoryQueryService's read-only cross-context precedent) —
        it stays pointing at whatever the last *recorded* activity was,
        same "approximate, documented" tradeoff already accepted for CRM-5's
        pipeline "stagnant" signal. lifecycle_stage is left untouched: a
        cancellation is not evidence of the relationship regressing."""
        if self.purchase_count > 0:
            self.purchase_count -= 1
        self._touch()

    # capability checks -------------------------------------------------------
    def is_operational(self) -> bool:
        return self.status is CustomerStatus.ACTIVE

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL
