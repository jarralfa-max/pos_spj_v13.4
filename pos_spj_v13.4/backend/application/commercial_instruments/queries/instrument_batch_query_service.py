"""Lectura de lotes de cupones y vales para la pantalla de Fidelidad.

Exige `GROWTH_ENGINE.lote.ver` en el backend (la ruta del menú no es frontera de
autorización). Las piezas se muestran por folio y por el PREFIJO de su código;
el código completo nunca sale de aquí (sólo al imprimir).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.loyalty.permissions import LoyaltyPermissions
from backend.infrastructure.db.repositories.commercial_instruments.unit_of_work import (
    CommercialInstrumentsUnitOfWork,
)

STATUS_LABELS = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Por aprobar", "APPROVED": "Aprobado",
    "PRINTED": "Impreso", "ACTIVATED": "Activo", "CANCELLED": "Cancelado",
}
PIECE_STATUS_LABELS = {"ISSUED": "Emitida", "ACTIVE": "Activa", "REVOKED": "Retirada"}
KIND_LABELS = {"COUPON": "Cupón", "VOUCHER": "Vale"}
MODE_LABELS = {"ONE_EVENT": "Un solo uso", "MULTI_EVENT": "Varios usos"}
FUNDING_LABELS = {"PROMOTIONAL": "Promocional (negocio)", "COMPENSATION": "Compensación",
                  "THIRD_PARTY": "Financiado por tercero", "PREPAID": "Prepagado"}


@dataclass(frozen=True)
class BatchRow:
    id: str
    name: str
    kind: str
    status: str
    quantity: int
    unit_value: Decimal
    mode: str
    max_percent_per_sale: Decimal | None
    funding: str
    valid_to: str
    printed_count: int
    created_by_user_id: str
    pieces_by_status: dict


@dataclass(frozen=True)
class PieceRow:
    id: str
    folio: str
    status: str
    code_hint: str
    print_count: int
    redemptions: int


class InstrumentBatchQueryService:
    def __init__(self, connection, *, authorization) -> None:
        self._conn = connection
        self._auth = authorization

    def batches(self, *, actor_user_id: str, limit: int = 200) -> tuple[BatchRow, ...]:
        self._auth.require(actor_user_id, LoyaltyPermissions.BATCH_VIEW)
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        return tuple(BatchRow(
            id=b.id, name=b.name, kind=b.kind.value, status=b.status.value,
            quantity=b.quantity, unit_value=b.unit_value, mode=b.redemption_mode.value,
            max_percent_per_sale=b.max_percent_per_sale, funding=b.funding_source.value,
            valid_to=(b.valid_to or "")[:10], printed_count=b.printed_count,
            created_by_user_id=b.created_by_user_id,
            pieces_by_status=uow.batch_items.counts(b.id))
            for b in uow.batches.list_recent(limit))

    def pieces(self, *, actor_user_id: str, batch_id: str) -> tuple[PieceRow, ...]:
        self._auth.require(actor_user_id, LoyaltyPermissions.BATCH_VIEW)
        uow = CommercialInstrumentsUnitOfWork(self._conn)
        filas = uow.batch_items.list_for_batch(batch_id)
        piezas = []
        for fila in filas:
            if fila["instance_kind"] == "VOUCHER":
                canjes = len(uow.voucher_redemptions.list_for_instance(fila["instance_id"]))
            else:
                instancia = uow.coupon_instances.get(fila["instance_id"])
                canjes = 1 if instancia is not None and instancia.status.value == "REDEEMED" else 0
            piezas.append(PieceRow(
                id=fila["id"], folio=fila["folio"], status=fila["status"],
                code_hint=f"{fila['token_prefix']}…", print_count=int(fila["print_count"]),
                redemptions=canjes))
        return tuple(piezas)


__all__ = ["BatchRow", "FUNDING_LABELS", "InstrumentBatchQueryService", "KIND_LABELS",
           "MODE_LABELS", "PIECE_STATUS_LABELS", "PieceRow", "STATUS_LABELS"]
