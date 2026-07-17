"""Supplier lifecycle use cases: create, update, submit, approve/reject,
activate/suspend, block/unblock.

Each: validates permission + state, runs in a UnitOfWork, records audit and
enqueues the canonical event to the outbox (dispatched post-commit). Idempotent
where an operation must not repeat (operation_id).
"""

from __future__ import annotations

import json

from backend.application.suppliers.authorization import SupplierAuthorizationPolicy
from backend.application.suppliers.permissions import SupplierPermissions
from backend.application.suppliers.result import SupplierResult
from backend.domain.suppliers.entities import Supplier, SupplierBlock
from backend.domain.suppliers.enums import (
    BlockType,
    CommercialCategory,
    SupplierClassification,
)
from backend.domain.suppliers.exceptions import PermissionDeniedError, SupplierDomainError
from backend.domain.suppliers.events import SupplierEvents, build_event_payload
from backend.domain.suppliers.policies import (
    SupplierActivationPolicy,
    SupplierApprovalPolicy,
    SupplierDuplicatePolicy,
)
from backend.domain.suppliers.value_objects import TaxIdentifier
from backend.infrastructure.db.repositories.suppliers.unit_of_work import SupplierUnitOfWork
from backend.shared.ids import new_uuid


class _BaseUseCase:
    def __init__(self, authorization: SupplierAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or SupplierAuthorizationPolicy()

    def _emit(self, uow, event_name: str, supplier_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      supplier_id=supplier_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)

    @staticmethod
    def _guard_permission(fn):
        return fn


class CreateSupplierUseCase(_BaseUseCase):
    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._duplicates = SupplierDuplicatePolicy()

    def execute(self, connection, *, actor_user_id: str, legal_name: str, operation_id: str,
                trade_name: str = "", tax_identifier: str | None = None,
                preferred_currency: str = "MXN",
                classifications: list[str] | None = None,
                categories: list[str] | None = None,
                allow_duplicate: bool = False) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.CREATE)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            existing = uow.suppliers.get_by_operation_id(operation_id)
            if existing is not None:
                return SupplierResult.ok("Proveedor ya registrado", entity_id=existing.id,
                                         operation_id=operation_id)
            if not allow_duplicate:
                candidate = {"tax_identifier": tax_identifier, "legal_name": legal_name,
                             "trade_name": trade_name}
                matches = self._duplicates.find_matches(candidate, uow.suppliers.find_duplicate_rows())
                if matches:
                    return SupplierResult.fail(
                        "Posible proveedor duplicado", "DUPLICATE", operation_id=operation_id,
                        duplicates=[{"supplier_id": m.supplier_id, "reasons": list(m.reasons)}
                                    for m in matches])
            try:
                supplier = Supplier.create(
                    uow.suppliers.next_code(), legal_name, trade_name=trade_name,
                    tax_identifier=TaxIdentifier(tax_identifier) if tax_identifier else None,
                    created_by_user_id=actor_user_id, preferred_currency=preferred_currency,
                    classifications={SupplierClassification(c) for c in (classifications or [])},
                    categories={CommercialCategory(c) for c in (categories or [])})
            except (SupplierDomainError, ValueError) as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.suppliers.save(supplier, operation_id=operation_id)
            uow.audit.record(action=SupplierEvents.CREATED, actor_user_id=actor_user_id,
                             supplier_id=supplier.id, after_json=json.dumps({"legal_name": legal_name}),
                             reason="alta", operation_id=operation_id)
            self._emit(uow, SupplierEvents.CREATED, supplier.id, operation_id, actor_user_id)
        return SupplierResult.ok("Proveedor creado", entity_id=supplier.id,
                                 operation_id=operation_id, code=str(supplier.code))


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""
    audit_action = ""

    def _apply(self, supplier: Supplier, *, actor_user_id: str, reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, supplier_id: str,
                operation_id: str, reason: str = "") -> SupplierResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            supplier = uow.suppliers.get(supplier_id)
            if supplier is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                self._apply(supplier, actor_user_id=actor_user_id, reason=reason)
            except SupplierDomainError as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.suppliers.update(supplier)
            uow.audit.record(action=self.audit_action or self.event_name,
                             actor_user_id=actor_user_id, supplier_id=supplier.id,
                             reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, supplier.id, operation_id, actor_user_id)
        return SupplierResult.ok("Operación registrada", entity_id=supplier_id,
                                 operation_id=operation_id)


class SubmitSupplierForApprovalUseCase(_TransitionUseCase):
    permission = SupplierPermissions.SUBMIT
    event_name = SupplierEvents.SUBMITTED_FOR_APPROVAL

    def _apply(self, supplier, *, actor_user_id, reason):
        supplier.submit_for_approval()


class ApproveSupplierUseCase(_TransitionUseCase):
    permission = SupplierPermissions.APPROVE
    event_name = SupplierEvents.APPROVED

    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._policy = SupplierApprovalPolicy()

    def _apply(self, supplier, *, actor_user_id, reason):
        self._policy.enforce_can_approve(supplier, actor_user_id)
        supplier.approve(actor_user_id)


class RejectSupplierUseCase(_TransitionUseCase):
    permission = SupplierPermissions.APPROVE
    event_name = SupplierEvents.REJECTED

    def _apply(self, supplier, *, actor_user_id, reason):
        supplier.reject(actor_user_id, reason)


class ActivateSupplierUseCase(_TransitionUseCase):
    permission = SupplierPermissions.ACTIVATE
    event_name = SupplierEvents.ACTIVATED

    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._policy = SupplierActivationPolicy()

    def _apply(self, supplier, *, actor_user_id, reason):
        self._policy.enforce_can_activate(supplier)
        supplier.activate()


class SuspendSupplierUseCase(_TransitionUseCase):
    permission = SupplierPermissions.SUSPEND
    event_name = SupplierEvents.SUSPENDED

    def _apply(self, supplier, *, actor_user_id, reason):
        supplier.suspend(reason)


class BlockSupplierUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str,
                block_type: str, reason: str, operation_id: str,
                expires_at: str | None = None,
                approved_by_user_id: str | None = None) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.BLOCK)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            supplier = uow.suppliers.get(supplier_id)
            if supplier is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                block = SupplierBlock.create(
                    supplier.id, BlockType(block_type), reason, actor_user_id, operation_id,
                    expires_at=expires_at, approved_by_user_id=approved_by_user_id)
                supplier.apply_block(block)
            except (SupplierDomainError, ValueError) as exc:
                return SupplierResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.suppliers.update(supplier)
            uow.audit.record(action=SupplierEvents.BLOCKED, actor_user_id=actor_user_id,
                             supplier_id=supplier.id, reason=reason, operation_id=operation_id)
            self._emit(uow, SupplierEvents.BLOCKED, supplier.id, operation_id, actor_user_id,
                       block_type=block_type)
        return SupplierResult.ok("Bloqueo aplicado", entity_id=supplier_id,
                                 operation_id=operation_id)


class UnblockSupplierUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str,
                block_type: str, operation_id: str, reason: str = "") -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.UNBLOCK)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            supplier = uow.suppliers.get(supplier_id)
            if supplier is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if not supplier.has_block(BlockType(block_type)):
                return SupplierResult.ok("El proveedor no tenía ese bloqueo",
                                         entity_id=supplier_id, operation_id=operation_id)
            supplier.remove_block(BlockType(block_type))
            uow.suppliers.update(supplier)
            uow.audit.record(action=SupplierEvents.UNBLOCKED, actor_user_id=actor_user_id,
                             supplier_id=supplier.id, reason=reason, operation_id=operation_id)
            self._emit(uow, SupplierEvents.UNBLOCKED, supplier.id, operation_id, actor_user_id,
                       block_type=block_type)
        return SupplierResult.ok("Bloqueo removido", entity_id=supplier_id,
                                 operation_id=operation_id)


class UpdateSupplierUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, supplier_id: str, operation_id: str,
                trade_name: str | None = None, website: str | None = None,
                notes: str | None = None, tax_regime: str | None = None) -> SupplierResult:
        try:
            self._auth.require(actor_user_id, SupplierPermissions.EDIT)
        except PermissionDeniedError as exc:
            return SupplierResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with SupplierUnitOfWork(connection) as uow:
            supplier = uow.suppliers.get(supplier_id)
            if supplier is None:
                return SupplierResult.fail("El proveedor no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            if trade_name is not None:
                supplier.trade_name = trade_name.strip()
            if website is not None:
                supplier.website = website
            if notes is not None:
                supplier.notes = notes
            if tax_regime is not None:
                supplier.tax_regime = tax_regime
            uow.suppliers.update(supplier)
            uow.audit.record(action=SupplierEvents.UPDATED, actor_user_id=actor_user_id,
                             supplier_id=supplier.id, reason="edición", operation_id=operation_id)
            self._emit(uow, SupplierEvents.UPDATED, supplier.id, operation_id, actor_user_id)
        return SupplierResult.ok("Proveedor actualizado", entity_id=supplier_id,
                                 operation_id=operation_id)
