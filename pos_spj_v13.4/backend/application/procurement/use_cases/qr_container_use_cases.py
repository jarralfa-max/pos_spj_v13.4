"""QR-container lifecycle use cases (migrated from the monolith): label
generation, container registration and container assignment.

A container's QR label is its UUID. Assignment records the supplier + products +
payment terms on the container's traceability so the later reception
(CompleteQrReceptionUseCase) carries the same context. Writes touch only the
traceability tables — never inventory/finance. Atomic (UoW), permission-gated.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.application.procurement.permissions import PurchasePermissions
from backend.application.procurement.result import ProcurementResult
from backend.domain.procurement.exceptions import PurchasePermissionDeniedError
from backend.infrastructure.db.repositories.procurement.unit_of_work import (
    ProcurementUnitOfWork,
)
from backend.shared.ids import new_uuid


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class RegisterQrContainerUseCase:
    """Generate a QR label (UUID) and register the container."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str,
                internal_code: str = "", description: str = "",
                origin_branch_id: str | None = None,
                uuid_qr: str | None = None) -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        code = uuid_qr or new_uuid()
        with ProcurementUnitOfWork(connection) as uow:
            uow.qr_containers.register_container(
                uuid_qr=code, internal_code=internal_code or code[:8],
                description=description, origin_branch_id=origin_branch_id)
        return ProcurementResult.ok("Contenedor QR generado", entity_id=code,
                                    operation_id=operation_id, uuid_qr=code)


class AssignQrContainerUseCase:
    """Assign a container to a supplier + products + payment terms."""

    def __init__(self, authorization: PurchaseAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or PurchaseAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, operation_id: str, uuid_qr: str,
                supplier_id: str, items: list[dict], payment_condition: str = "liquidado",
                payment_method: str = "efectivo", amount_paid: str | None = None,
                origin_branch_id: str | None = None,
                destination_branch_id: str | None = None,
                notes: str = "") -> ProcurementResult:
        try:
            self._auth.require(actor_user_id, PurchasePermissions.RECEIPT_CREATE)
        except PurchasePermissionDeniedError as exc:
            return ProcurementResult.fail(str(exc), "PERMISSION_DENIED",
                                          operation_id=operation_id)
        if not supplier_id:
            return ProcurementResult.fail("La asignación requiere proveedor", "VALIDATION",
                                          operation_id=operation_id)
        if not items:
            return ProcurementResult.fail("La asignación requiere al menos un producto",
                                          "EMPTY", operation_id=operation_id)

        def _qty(it):
            return _dec(it.get("cantidad") or it.get("quantity"))

        def _cost(it):
            return _dec(it.get("costo_unitario") or it.get("unit_cost") or it.get("unit_price"))

        total = sum((_qty(it) * _cost(it) for it in items), Decimal("0"))
        # payment terms mirror the legacy widget: liquidado ⇒ paid = total;
        # crédito ⇒ paid = 0; otherwise use the explicit amount_paid.
        if payment_condition == "liquidado":
            paid = total
        elif payment_condition in ("crédito", "credito"):
            paid = Decimal("0")
        else:
            paid = _dec(amount_paid)

        datos_extra = {
            "proveedor_id": supplier_id,
            "condicion_pago": payment_condition,
            "metodo_pago": payment_method,
            "monto_total": str(total),
            "monto_pagado": str(paid),
            "items": [{"product_id": str(it.get("product_id") or it.get("producto_id")),
                       "cantidad": str(_qty(it)), "costo_unitario": str(_cost(it))}
                      for it in items],
            "notas": notes,
        }
        with ProcurementUnitOfWork(connection) as uow:
            uow.qr_containers.save_assignment(
                uuid_qr=uuid_qr, supplier_id=supplier_id, origin_branch_id=origin_branch_id,
                destination_branch_id=destination_branch_id, datos_extra=datos_extra)
        return ProcurementResult.ok("Contenedor asignado", entity_id=uuid_qr,
                                    operation_id=operation_id, total=str(total),
                                    amount_paid=str(paid))
