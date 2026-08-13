"""CustomerMergeRecord — a proposed-then-executed customer merge (§45).

"Fusión: selecciona maestro, preserva referencias, resuelve contactos/
direcciones/consentimientos/crédito/propietario, notifica bounded
contexts, audita — nunca modifica tablas externas directamente." This
entity is the audit trail of that decision; the actual data resolution is
ExecuteCustomerMergeUseCase's job, and it only ever touches ``customers``'
own tables (contacts/addresses/tax profile) — cross-context data
(consentimientos/crédito/propietario in customer_privacy/customer_credit/
crm) is notified via the CUSTOMER_MERGE_EXECUTED event, never written
directly, same bounded-context boundary CRM-8/CRM-9 already held.

Status transitions:

    PROPOSED ──execute()──► EXECUTED   (hot-authorized, §74 — see
                                        ExecuteCustomerMergeUseCase)
    PROPOSED ──reject(reason)──► REJECTED

No separate persisted "APPROVED" state: approval and execution happen
atomically in one hot-authorized call, same collapsing UpdateCustomer
CreditLimitUseCase(override=True) already does for credit-limit overrides
— nothing meaningful happens between "approved" and "executed" that would
need its own state or use case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.enums import CustomerMergeStatus
from backend.domain.customers.exceptions import InvalidCustomerMergeStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_EXECUTABLE = {CustomerMergeStatus.PROPOSED}
_REJECTABLE = {CustomerMergeStatus.PROPOSED}


@dataclass(slots=True)
class CustomerMergeRecord:
    id: str
    master_customer_id: str
    merged_customer_id: str
    proposed_by_user_id: str
    duplicate_candidate_id: str | None = None
    reason: str = ""
    status: CustomerMergeStatus = CustomerMergeStatus.PROPOSED
    executed_by_user_id: str | None = None
    executed_at: str | None = None
    rejected_by_user_id: str | None = None
    rejected_at: str | None = None
    rejection_reason: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    @classmethod
    def propose(
        cls, master_customer_id: str, merged_customer_id: str, proposed_by_user_id: str, *,
        duplicate_candidate_id: str | None = None, reason: str = "",
        operation_id: str | None = None,
    ) -> "CustomerMergeRecord":
        if not master_customer_id or not merged_customer_id:
            raise InvalidCustomerMergeStateError(
                "master_customer_id y merged_customer_id son obligatorios")
        if master_customer_id == merged_customer_id:
            raise InvalidCustomerMergeStateError(
                "El cliente maestro y el fusionado no pueden ser el mismo")
        if not proposed_by_user_id:
            raise InvalidCustomerMergeStateError("proposed_by_user_id es obligatorio")
        return cls(
            id=new_uuid(), master_customer_id=master_customer_id,
            merged_customer_id=merged_customer_id, proposed_by_user_id=proposed_by_user_id,
            duplicate_candidate_id=duplicate_candidate_id, reason=reason.strip(),
            operation_id=operation_id,
        )

    def execute(self, executed_by_user_id: str) -> None:
        if self.status not in _EXECUTABLE:
            raise InvalidCustomerMergeStateError(
                f"No se puede ejecutar desde {self.status.value}")
        self.status = CustomerMergeStatus.EXECUTED
        self.executed_by_user_id = executed_by_user_id
        self.executed_at = _utcnow()
        self._touch()

    def reject(self, rejected_by_user_id: str, reason: str) -> None:
        if self.status not in _REJECTABLE:
            raise InvalidCustomerMergeStateError(
                f"No se puede rechazar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCustomerMergeStateError("Rechazar requiere un motivo")
        self.status = CustomerMergeStatus.REJECTED
        self.rejected_by_user_id = rejected_by_user_id
        self.rejected_at = _utcnow()
        self.rejection_reason = reason.strip()
        self._touch()
