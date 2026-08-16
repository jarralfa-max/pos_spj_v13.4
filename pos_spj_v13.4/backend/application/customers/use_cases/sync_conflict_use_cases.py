"""Customer Master offline-first sync conflicts (§91-92, CRM-20).

``DetectCustomerSyncConflictUseCase`` is the concrete enforcement of "no
sobrescribir silenciosamente": an incoming remote/offline-queued mutation
must carry the ``base_version`` it was edited against. If that no longer
matches the customer's current ``version`` (CRM-3, optimistic concurrency —
already bumped on every mutation via ``Customer.record_edit()``), someone
else's change landed first. The incoming change is NEVER applied
automatically; a ``CustomerSyncConflict`` row is created instead and the
caller gets a failed, explicit result — the same "block, don't clobber"
contract every other write path in this bounded context already holds for
permissions/scope, just applied to concurrent writes.

``ResolveCustomerSyncConflictUseCase`` is the only path that can close a
conflict — permission-gated, explicit outcome (LOCAL/REMOTE/MERGED),
always audited.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer_sync_conflict import CustomerSyncConflict
from backend.domain.customers.enums import CustomerSyncConflictType, SyncConflictStatus
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork

_RESOLUTION_MAP = {
    "LOCAL": SyncConflictStatus.RESOLVED_LOCAL,
    "REMOTE": SyncConflictStatus.RESOLVED_REMOTE,
    "MERGED": SyncConflictStatus.RESOLVED_MERGED,
}

# Only these Customer fields are safe to apply from a remote/merged snapshot
# — identity/lifecycle fields (status, code, id) are never touched by a
# sync conflict resolution, only the same editable fields
# UpdateCustomerUseCase itself exposes (mirrors that use case's own field
# allowlist, doesn't invent a wider write surface for this path).
_APPLICABLE_FIELDS = ("display_name", "legal_name", "commercial_name")


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str | None, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class DetectCustomerSyncConflictUseCase(_BaseUseCase):
    """No actor_user_id/permission check — this runs as part of applying an
    incoming sync mutation (system-triggered), same reasoning
    CRM-13/CRM-26 already established for other system-reactive use cases.
    Detecting a conflict is not a privileged action; RESOLVING one is."""

    def execute(
        self, connection, *, customer_id: str, base_version: int, remote_snapshot: dict,
        operation_id: str, conflict_type: str = CustomerSyncConflictType.CUSTOMER_UPDATED_REMOTELY.value,
        detail: str = "",
    ) -> CustomerResult:
        with CustomerUnitOfWork(connection) as uow:
            customer = uow.customers.get(customer_id)
            if customer is None:
                return CustomerResult.fail("El cliente no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if customer.version == base_version:
                return CustomerResult.ok("Sin conflicto — versión vigente", entity_id=customer_id,
                                         operation_id=operation_id, conflict=False)
            try:
                conflict = CustomerSyncConflict.detect(
                    customer_id, CustomerSyncConflictType(conflict_type), base_version,
                    remote_snapshot, detail=detail, operation_id=operation_id)
            except (CustomerDomainError, ValueError) as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.sync_conflicts.save(conflict)
            uow.audit.record(action=CustomerEvents.SYNC_CONFLICT_DETECTED, actor_user_id=None,
                             customer_id=customer_id, operation_id=operation_id,
                             after_json=json.dumps({"conflict_id": conflict.id,
                                                    "conflict_type": conflict.conflict_type.value}))
            self._emit(uow, CustomerEvents.SYNC_CONFLICT_DETECTED, customer_id, operation_id, None,
                      conflict_id=conflict.id, conflict_type=conflict.conflict_type.value)
        return CustomerResult.fail(
            "Conflicto de sincronización: la versión local cambió, el cambio remoto no se aplicó",
            "SYNC_CONFLICT", operation_id=operation_id, conflict=True, conflict_id=conflict.id)


class ResolveCustomerSyncConflictUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, conflict_id: str, resolution: str,
        operation_id: str, resolution_note: str = "", merged_fields: dict | None = None,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.SYNC_CONFLICTS_RESOLVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        outcome = _RESOLUTION_MAP.get(resolution)
        if outcome is None:
            return CustomerResult.fail(
                "resolution debe ser LOCAL, REMOTE o MERGED", "VALIDATION",
                operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            conflict = uow.sync_conflicts.get(conflict_id)
            if conflict is None:
                return CustomerResult.fail("El conflicto no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                conflict.resolve(outcome, resolved_by_user_id=actor_user_id,
                                 resolution_note=resolution_note)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

            if outcome != SyncConflictStatus.RESOLVED_LOCAL:
                customer = uow.customers.get(conflict.customer_id)
                if customer is not None:
                    source = merged_fields if outcome == SyncConflictStatus.RESOLVED_MERGED \
                        else conflict.remote_snapshot
                    for field_name in _APPLICABLE_FIELDS:
                        if source and field_name in source and source[field_name] is not None:
                            setattr(customer, field_name, source[field_name])
                    customer.record_edit()
                    uow.customers.update(customer)

            uow.sync_conflicts.update(conflict)
            uow.audit.record(action=CustomerEvents.SYNC_CONFLICT_RESOLVED,
                             actor_user_id=actor_user_id, customer_id=conflict.customer_id,
                             operation_id=operation_id, reason=resolution_note,
                             after_json=json.dumps({"conflict_id": conflict.id,
                                                    "outcome": outcome.value}))
            self._emit(uow, CustomerEvents.SYNC_CONFLICT_RESOLVED, conflict.customer_id,
                      operation_id, actor_user_id, conflict_id=conflict.id, outcome=outcome.value)
        return CustomerResult.ok("Conflicto resuelto", entity_id=conflict_id,
                                 operation_id=operation_id, outcome=outcome.value)
