"""Lotes físicos de cupones y vales (auditoría de Fidelidad 968e0bc, ampliación).

Ciclo y efectos:

1. **Crear** (`DRAFT`) y **enviar** a aprobación: sólo papel; nada se emite.
2. **Aprobar** (otra persona): genera las piezas — una instancia por pieza con su
   folio y la huella de su código —, todas en `ISSUED`: existen pero NO se pueden
   canjear. Sin efecto contable.
3. **Imprimir** (y reimprimir): entrega los códigos al renderizador. Reimprimir da
   los MISMOS códigos (se derivan, no se guardan).
4. **Activar**: las piezas pasan a `ACTIVE`; los vales reciben su saldo en el libro
   y publican `VOUCHER_ISSUED`, que es cuando Finanzas reconoce el pasivo. Antes
   no: aprobar mil vales que siguen en una caja no es deuda con nadie.
5. **Cancelar** (antes de activar) o **revocar** una pieza extraviada (rota su
   código: el impreso deja de servir).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.commercial_instruments.result import (
    CommercialInstrumentResult,
    fail_from_domain_error,
)
from backend.application.commercial_instruments.use_cases._base import (
    _CommercialInstrumentBaseUseCase,
)
from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.instrument_batch import (
    InstrumentBatch,
    InstrumentKind,
)
from backend.domain.commercial_instruments.entities.voucher_instance import VoucherInstance
from backend.domain.commercial_instruments.entities.voucher_transaction import VoucherTransaction
from backend.domain.commercial_instruments.enums import (
    CouponInstanceStatus,
    VoucherInstanceStatus,
    VoucherType,
)
from backend.domain.commercial_instruments.events import CommercialInstrumentEvents
from backend.domain.commercial_instruments.exceptions import CommercialInstrumentDomainError
from backend.domain.commercial_instruments.value_objects.piece_code import (
    hash_piece_code,
    printable_piece_code,
)
from backend.domain.commercial_instruments.value_objects.redemption_rules import (
    FundingSource,
    LeftoverPolicy,
    PercentBase,
    RedemptionMode,
)
from backend.domain.loyalty.exceptions import LoyaltyDomainError
from backend.infrastructure.commercial_instruments.piece_token import piece_codec_for
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
    CommercialInstrumentsUnitOfWork,
)
from backend.shared.ids import new_uuid

_TOKEN_PREFIX_LENGTH = 6


@dataclass(frozen=True)
class PrintablePiece:
    """Lo que el renderizador necesita de una pieza. El código sólo existe aquí,
    en memoria, mientras se imprime."""

    folio: str
    code: str
    kind: str
    value: Decimal
    valid_to: str | None
    sequence_no: int


def _folio(batch: InstrumentBatch, sequence_no: int) -> str:
    return f"{batch.kind.prefix}{batch.id[-4:].upper()}-{sequence_no:05d}"


class _BatchUseCase(_CommercialInstrumentBaseUseCase):
    def _guard(self, actor_user_id: str, permiso: str, operation_id: str):
        try:
            self._auth.require(actor_user_id, permiso)
        except LoyaltyDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return None

    @staticmethod
    def _load(uow, batch_id: str, operation_id: str):
        lote = uow.batches.get(batch_id)
        if lote is None:
            return None, CommercialInstrumentResult.fail(
                "El lote no existe", "NOT_FOUND", operation_id=operation_id)
        return lote, None


class CreateInstrumentBatchUseCase(_BatchUseCase):
    def execute(self, connection, *, actor_user_id: str, actor_branch_id: str,
                operation_id: str, kind: str, definition_id: str, name: str, quantity: int,
                funding_source: str, unit_value: Decimal | None = None,
                valid_from: str | None = None, valid_to: str | None = None,
                branch_ids: tuple[str, ...] = (), redemption_mode: str = "MULTI_EVENT",
                max_redemptions: int | None = None,
                max_percent_per_sale: Decimal | None = None, percent_base: str = "GROSS",
                leftover_policy: str = "REQUIRE_FULL_USE") -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_CREATE,
                                    operation_id)) is not None:
            return denegado
        try:
            tipo = InstrumentKind(kind)
            with CommercialInstrumentsUnitOfWork(connection) as uow:
                if tipo is InstrumentKind.COUPON:
                    definicion = uow.coupon_definitions.get(definition_id)
                    if definicion is None:
                        return CommercialInstrumentResult.fail(
                            "La definición de cupón no existe", "NOT_FOUND",
                            operation_id=operation_id)
                    valor = Decimal(str(definicion.benefit_value))
                else:
                    definicion = uow.voucher_definitions.get(definition_id)
                    if definicion is None:
                        return CommercialInstrumentResult.fail(
                            "La definición de vale no existe", "NOT_FOUND",
                            operation_id=operation_id)
                    if definicion.voucher_type is VoucherType.PREPAID_VOUCHER:
                        return CommercialInstrumentResult.fail(
                            "Los vales prepagados se venden en el punto de venta, uno por uno.",
                            "VALIDATION", operation_id=operation_id)
                    valor = Decimal(str(unit_value or "0"))
                lote = InstrumentBatch.draft(
                    kind=tipo, definition_id=definition_id, name=name, quantity=int(quantity),
                    unit_value=valor, funding_source=FundingSource(funding_source),
                    created_by_user_id=actor_user_id, valid_from=valid_from or None,
                    valid_to=valid_to or None, branch_ids=tuple(b for b in branch_ids if b),
                    redemption_mode=RedemptionMode(redemption_mode),
                    max_redemptions=max_redemptions,
                    max_percent_per_sale=max_percent_per_sale,
                    percent_base=PercentBase(percent_base),
                    leftover_policy=LeftoverPolicy(leftover_policy))
                uow.batches.save(lote)
                self._audit(uow, "INSTRUMENT_BATCH_CREATED", entity_id=lote.id,
                            operation_id=operation_id, branch_id=actor_branch_id,
                            actor_user_id=actor_user_id, kind=lote.kind.value,
                            quantity=lote.quantity, unit_value=str(lote.unit_value))
        except (CommercialInstrumentDomainError, ValueError) as exc:
            return CommercialInstrumentResult.fail(str(exc), "VALIDATION",
                                                   operation_id=operation_id)
        return CommercialInstrumentResult.ok("Lote creado en borrador", entity_id=lote.id,
                                             operation_id=operation_id)


class SubmitInstrumentBatchUseCase(_BatchUseCase):
    def execute(self, connection, *, batch_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_CREATE,
                                    operation_id)) is not None:
            return denegado
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            lote, error = self._load(uow, batch_id, operation_id)
            if error:
                return error
            try:
                lote.submit()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            uow.batches.save(lote)
            self._audit(uow, "INSTRUMENT_BATCH_SUBMITTED", entity_id=lote.id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id)
        return CommercialInstrumentResult.ok("Lote enviado a aprobación", entity_id=lote.id,
                                             operation_id=operation_id)


class ApproveInstrumentBatchUseCase(_BatchUseCase):
    def execute(self, connection, *, batch_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_APPROVE,
                                    operation_id)) is not None:
            return denegado
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            lote, error = self._load(uow, batch_id, operation_id)
            if error:
                return error
            try:
                lote.approve(actor_user_id)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            codec = piece_codec_for(uow.connection)
            for secuencia in range(1, lote.quantity + 1):
                folio = _folio(lote, secuencia)
                if lote.kind is InstrumentKind.COUPON:
                    pieza = CouponInstance.issue(lote.definition_id, folio)
                    pieza.status = CouponInstanceStatus.ISSUED
                    uow.coupon_instances.save(pieza)
                else:
                    pieza = VoucherInstance.issue(
                        lote.definition_id, folio,
                        expires_at=f"{lote.valid_to[:10]}T23:59:59+00:00" if lote.valid_to
                        else None)
                    pieza.status = VoucherInstanceStatus.ISSUED
                    uow.voucher_instances.save(pieza)
                    uow.voucher_rules.save(voucher_instance_id=pieza.id, batch=lote)
                item_id = new_uuid()
                codigo = codec.derive(prefix=lote.kind.prefix, item_id=item_id, version=1)
                uow.batch_items.add(
                    item_id=item_id, batch_id=lote.id, sequence_no=secuencia, folio=folio,
                    instance_kind=lote.kind.value, instance_id=pieza.id,
                    token_hash=hash_piece_code(codigo),
                    token_prefix=codigo[:_TOKEN_PREFIX_LENGTH])
            uow.batches.save(lote)
            self._audit(uow, "INSTRUMENT_BATCH_APPROVED", entity_id=lote.id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id, quantity=lote.quantity)
        return CommercialInstrumentResult.ok(
            f"Lote aprobado: {lote.quantity} piezas emitidas (aún no canjeables).",
            entity_id=lote.id, operation_id=operation_id)


class PrintInstrumentBatchUseCase(_BatchUseCase):
    """Devuelve las piezas imprimibles y deja constancia de la (re)impresión. No
    renderiza: eso lo hace la infraestructura (PDF o térmica)."""

    def execute(self, connection, *, batch_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_PRINT,
                                    operation_id)) is not None:
            return denegado
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            lote, error = self._load(uow, batch_id, operation_id)
            if error:
                return error
            reimpresion = lote.printed_count > 0
            try:
                lote.mark_printed()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            codec = piece_codec_for(uow.connection)
            piezas = tuple(
                PrintablePiece(
                    folio=fila["folio"],
                    code=printable_piece_code(codec.derive(
                        prefix=lote.kind.prefix, item_id=fila["id"],
                        version=int(fila["token_version"]))),
                    kind=lote.kind.value, value=lote.unit_value, valid_to=lote.valid_to,
                    sequence_no=int(fila["sequence_no"]))
                for fila in uow.batch_items.list_for_batch(lote.id)
                if fila["status"] != "REVOKED")
            uow.batch_items.mark_printed(lote.id)
            uow.batches.save(lote)
            self._audit(uow, "INSTRUMENT_BATCH_REPRINTED" if reimpresion
                        else "INSTRUMENT_BATCH_PRINTED", entity_id=lote.id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id, pieces=len(piezas),
                        print_number=lote.printed_count)
        return CommercialInstrumentResult.ok(
            f"{len(piezas)} piezas listas para imprimir"
            + (f" (reimpresión {lote.printed_count - 1})" if reimpresion else ""),
            entity_id=lote.id, operation_id=operation_id, pieces=piezas, batch_name=lote.name)


class ActivateInstrumentBatchUseCase(_BatchUseCase):
    def execute(self, connection, *, batch_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str, currency_code: str = "MXN") -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_APPROVE,
                                    operation_id)) is not None:
            return denegado
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            lote, error = self._load(uow, batch_id, operation_id)
            if error:
                return error
            try:
                lote.activate()
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            activadas = 0
            for fila in uow.batch_items.list_for_batch(lote.id):
                if fila["status"] == "REVOKED":
                    continue
                # Cada pieza es su propia operación (UUIDv7); activar dos veces el
                # mismo lote lo impide su estado, no un sufijo en el id.
                operacion_pieza = new_uuid()
                if lote.kind is InstrumentKind.COUPON:
                    pieza = uow.coupon_instances.get(fila["instance_id"])
                    pieza.activate()
                    uow.coupon_instances.save(pieza)
                    evento = CommercialInstrumentEvents.COUPON_ISSUED
                else:
                    pieza = uow.voucher_instances.get(fila["instance_id"])
                    pieza.activate()
                    uow.voucher_instances.save(pieza)
                    uow.voucher_transactions.save(VoucherTransaction.issue(
                        voucher_instance_id=pieza.id, amount=lote.unit_value,
                        operation_id=operacion_pieza, created_by_user_id=actor_user_id))
                    evento = CommercialInstrumentEvents.VOUCHER_ISSUED
                self._emit(uow, evento, entity_id=pieza.id,
                           operation_id=operacion_pieza, branch_id=actor_branch_id, actor_user_id=actor_user_id,
                           instrument_id=pieza.id, face_value=str(lote.unit_value),
                           currency_code=currency_code, customer_id=None,
                           source_module="commercial_instruments", batch_id=lote.id,
                           funding_source=lote.funding_source.value,
                           batch_operation_id=operation_id)
                activadas += 1
            uow.batch_items.set_status(lote.id, "ACTIVE", only_from=("ISSUED",))
            uow.batches.save(lote)
            self._audit(uow, "INSTRUMENT_BATCH_ACTIVATED", entity_id=lote.id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id, pieces=activadas)
        return CommercialInstrumentResult.ok(f"Lote activado: {activadas} piezas canjeables.",
                                             entity_id=lote.id, operation_id=operation_id)


class CancelInstrumentBatchUseCase(_BatchUseCase):
    def execute(self, connection, *, batch_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_APPROVE,
                                    operation_id)) is not None:
            return denegado
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            lote, error = self._load(uow, batch_id, operation_id)
            if error:
                return error
            try:
                lote.cancel(reason)
            except CommercialInstrumentDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)
            for fila in uow.batch_items.list_for_batch(lote.id):
                repo = (uow.coupon_instances if lote.kind is InstrumentKind.COUPON
                        else uow.voucher_instances)
                pieza = repo.get(fila["instance_id"])
                if pieza is not None and pieza.status.value == "ISSUED":
                    pieza.cancel(reason.strip())
                    repo.save(pieza)
            uow.batch_items.set_status(lote.id, "REVOKED", only_from=("ISSUED",))
            uow.batches.save(lote)
            self._audit(uow, "INSTRUMENT_BATCH_CANCELLED", entity_id=lote.id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id, reason=reason.strip())
        return CommercialInstrumentResult.ok("Lote cancelado", entity_id=lote.id,
                                             operation_id=operation_id)


class RevokeBatchPieceUseCase(_BatchUseCase):
    """Una pieza extraviada: su código impreso deja de servir (se rota). Si se
    pide `reissue`, devuelve el código NUEVO para imprimir sólo esa pieza."""

    def execute(self, connection, *, item_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str,
                reissue: bool = True) -> CommercialInstrumentResult:
        if (denegado := self._guard(actor_user_id, LoyaltyPermissions.BATCH_REVOKE,
                                    operation_id)) is not None:
            return denegado
        if not str(reason or "").strip():
            return CommercialInstrumentResult.fail("Revocar una pieza requiere motivo",
                                                   "VALIDATION", operation_id=operation_id)
        with CommercialInstrumentsUnitOfWork(connection) as uow:
            fila = uow.batch_items.get(item_id)
            if fila is None or fila["status"] == "REVOKED":
                return CommercialInstrumentResult.fail("La pieza no existe o ya está revocada",
                                                       "NOT_FOUND", operation_id=operation_id)
            lote = uow.batches.get(fila["batch_id"])
            version = int(fila["token_version"]) + 1
            codec = piece_codec_for(uow.connection)
            nuevo = codec.derive(prefix=lote.kind.prefix, item_id=item_id, version=version)
            uow.batch_items.rotate_token(item_id, token_hash=hash_piece_code(nuevo),
                                         token_prefix=nuevo[:_TOKEN_PREFIX_LENGTH],
                                         token_version=version)
            if not reissue:
                uow.batch_items.revoke(item_id, reason.strip())
            self._audit(uow, "INSTRUMENT_PIECE_REVOKED", entity_id=item_id,
                        operation_id=operation_id, branch_id=actor_branch_id,
                        actor_user_id=actor_user_id, folio=fila["folio"],
                        reason=reason.strip(), reissued=bool(reissue))
        datos = {"folio": fila["folio"], "batch_name": lote.name}
        if reissue:
            datos["code"] = printable_piece_code(nuevo)
            datos["piece"] = PrintablePiece(
                folio=fila["folio"], code=datos["code"], kind=lote.kind.value,
                value=lote.unit_value, valid_to=lote.valid_to,
                sequence_no=int(fila["sequence_no"]))
        return CommercialInstrumentResult.ok(
            "Código anterior anulado" + ("; imprime la pieza con su código nuevo" if reissue
                                         else "; pieza retirada"),
            entity_id=item_id, operation_id=operation_id, **datos)


__all__ = [
    "ActivateInstrumentBatchUseCase", "ApproveInstrumentBatchUseCase",
    "CancelInstrumentBatchUseCase", "CreateInstrumentBatchUseCase", "PrintInstrumentBatchUseCase",
    "PrintablePiece", "RevokeBatchPieceUseCase", "SubmitInstrumentBatchUseCase",
]
