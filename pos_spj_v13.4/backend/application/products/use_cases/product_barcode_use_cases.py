"""Use cases de códigos de barras y códigos alternos (PROD-7).

`BarcodeRepository.assign()` ya enforced unicidad activa vía
`barcode_uniqueness_policy.ensure_barcode_assignable()` — pero hasta esta fase
tenía CERO llamadores reales (confirmado por grep): el único consumidor de
`BarcodeRepository` era una lectura (`active_owner`) en
`product_query_service.py`; nada en la aplicación podía asignar un código de
barras, un código de báscula, un QR o un código alterno a un producto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_barcode_commands import (
    AddAlternateCodeCommand,
    AssignBarcodeCommand,
    SetBarcodeActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.security.unwired_policy import unwired
from backend.domain.products.entities.product_alternate_code import (
    ProductAlternateCode,
)
from backend.domain.products.entities.product_barcode import ProductBarcode
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.value_objects.barcode import Barcode
from backend.infrastructure.db.repositories.products.barcode_repository import (
    BarcodeRepository,
)

logger = logging.getLogger("spj.products.barcode_use_cases")


@dataclass(frozen=True)
class BarcodeResult:
    success: bool
    entity_id: str | None
    message: str


class _Base:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = BarcodeRepository(connection)
        self._auth = authorization or unwired(ProductsAuthorizationPolicy)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class AssignBarcodeUseCase(_Base):
    name = "AssignBarcodeUseCase"

    def execute(self, command: AssignBarcodeCommand) -> BarcodeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.BARCODES_MANAGE)
        try:
            barcode_vo = Barcode(value=command.value, barcode_type=command.barcode_type)
            pb = ProductBarcode(product_id=command.product_id, barcode=barcode_vo,
                                variant_id=command.variant_id,
                                is_primary=bool(command.is_primary))
        except ProductsDomainError as exc:
            return BarcodeResult(False, None, str(exc))
        # PROD-22: reasignar el mismo código al mismo producto no cambia nada;
        # antes dejaba auditoría y evento de una asignación que no ocurrió.
        if self._repo.active_owner(pb.value) == command.product_id and not command.is_primary:
            return BarcodeResult(True, None, "El código ya estaba asignado a este producto")
        try:
            stage_barcode_assignment(self._conn, pb, user_id=command.user_id,
                                     operation_id=command.operation_id)
            self._conn.commit()
        except ProductsDomainError as exc:
            self._rollback()
            return BarcodeResult(False, None, str(exc))
        except Exception:
            self._rollback()
            logger.exception("assign barcode failed op=%s", command.operation_id)
            raise
        return BarcodeResult(True, pb.id, "PRODUCT_BARCODE_ASSIGNED")


class SetBarcodeActiveUseCase(_Base):
    name = "SetBarcodeActiveUseCase"

    def execute(self, command: SetBarcodeActiveCommand) -> BarcodeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.BARCODES_MANAGE)
        barcode = self._repo.get(command.barcode_id)
        if barcode is None:
            return BarcodeResult(False, None, "El código de barras no existe")
        try:
            self._repo.set_active(command.barcode_id, command.active)
            record_product_audit_entry(
                self._conn, action="PRODUCT_BARCODE_UPDATED",
                entity_id=barcode.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"barcode_id": command.barcode_id, "active": command.active})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active barcode failed op=%s", command.operation_id)
            raise
        return BarcodeResult(True, command.barcode_id, "PRODUCT_BARCODE_UPDATED")


class AddAlternateCodeUseCase(_Base):
    name = "AddAlternateCodeUseCase"

    def execute(self, command: AddAlternateCodeCommand) -> BarcodeResult:
        command.validate()
        self._auth.require(command.user_id or "",
                           ProductPermissions.ALTERNATE_CODES_MANAGE)
        try:
            code = ProductAlternateCode(
                product_id=command.product_id, code=command.code,
                code_type=command.code_type, supplier_id=command.supplier_id)
        except ProductsDomainError as exc:
            return BarcodeResult(False, None, str(exc))
        try:
            self._repo.add_alternate_code(code)
            record_product_audit_entry(
                self._conn, action="PRODUCT_ALTERNATE_CODE_ADDED",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"code": code.code, "code_type": code.code_type})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("add alternate code failed op=%s", command.operation_id)
            raise
        return BarcodeResult(True, code.id, "PRODUCT_ALTERNATE_CODE_ADDED")


def stage_barcode_assignment(conn, pb: ProductBarcode, *, user_id: str | None,
                             operation_id: str) -> None:
    """Asigna el código (unicidad activa, principal único, consecutivo interno,
    auditoría y evento) SIN commit: lo usan la asignación suelta y el alta del
    producto con su código de barras inicial (PROD-23), en una sola transacción.
    Lanza ``ProductsDomainError`` si el código ya pertenece a otro producto."""
    from types import SimpleNamespace

    from backend.application.products.queries.internal_barcode import (
        advance_internal_barcode_sequence,
    )
    repo = BarcodeRepository(conn)
    repo.assign(pb)
    if pb.is_primary:
        repo.make_primary(pb.product_id, pb.value)
    advance_internal_barcode_sequence(conn, pb.value)
    record_product_audit_entry(
        conn, action="PRODUCT_BARCODE_ASSIGNED", entity_id=pb.product_id,
        user_id=user_id, operation_id=operation_id,
        after={"barcode_id": pb.id, "value": pb.value,
               "barcode_type": pb.barcode.barcode_type.value})
    _emit(conn, ProductEvents.PRODUCT_BARCODE_ASSIGNED,
          SimpleNamespace(operation_id=operation_id), pb.product_id,
          {"barcode_id": pb.id, "value": pb.value})


def _emit(conn, event_name: str, command, entity_id: str, extra: dict) -> None:
    import json
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
              "operation_id": command.operation_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, entity_id,
         json.dumps(payload)))
