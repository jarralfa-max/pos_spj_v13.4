"""Read model and Decimal projections for CASH-8."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class LedgerReader(Protocol):
    def list_for_shift(self, shift_id: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class LedgerRow:
    id: str
    recorded_at: str
    movement_type: str
    concept: str
    direction: str
    #: None = importe oculto (arqueo ciego abierto o turno ajeno sin permiso).
    amount: Decimal | None
    balance: Decimal | None
    reversal_of_id: str | None
    reference_id: str | None
    related_sale_id: str | None
    #: Auditoría CJA-05: «Venta V-COR-000008», «Apertura del turno»; nunca un id.
    origin_label: str = ""
    #: «Retiro manual de las 10:32» — el movimiento que este revierte.
    reversal_label: str = ""


@dataclass(frozen=True, slots=True)
class LedgerProjection:
    shift_id: str
    balance: Decimal | None
    inflows: Decimal | None
    outflows: Decimal | None
    movement_count: int
    rows: tuple[LedgerRow, ...]
    #: Auditoría CJA-01: por qué no se muestran importes (None = se muestran).
    hidden_reason: str | None = None


class CashLedgerQueryService:
    """Auditoría CJA-01 (2026-10-16): con `authorization` (la composición real
    lo inyecta) la proyección exige usuario y sucursal, `CAJA.movimiento.ver`,
    que el turno sea de esa sucursal, y oculta los importes según
    `CashAmountVisibility`. Antes no recibía ni usuario ni sucursal y entregaba
    el saldo que el arqueo ciego oculta."""

    def __init__(self, reader: LedgerReader, *, connection=None, authorization=None) -> None:
        self._reader = reader
        self._conn = connection
        self._auth = authorization

    def projection(self, shift_id: str, *, requester_user_id: str | None = None,
                   branch_id: str | None = None) -> LedgerProjection:
        full = self._full_projection(shift_id)
        if self._auth is None:
            return full
        from backend.application.cash_register.amount_visibility import CashAmountVisibility
        from backend.application.cash_register.permissions import CashPermissions
        from backend.domain.cash_register.exceptions import CashInvalidStateError

        self._auth.require(user_id=requester_user_id or "",
                           permission_code=CashPermissions.MOVEMENT_VIEW,
                           branch_id=branch_id or "")
        shift = self._conn.execute(
            "SELECT branch_id, cashier_user_id FROM cash_shifts WHERE id=?",
            (shift_id,)).fetchone()
        if shift is None or shift[0] != branch_id:
            raise CashInvalidStateError("Turno no encontrado en la sucursal")
        if CashAmountVisibility(self._conn, self._auth).shift_amounts_visible(
                shift_id=shift_id, cashier_user_id=shift[1],
                requester_user_id=requester_user_id or "", branch_id=branch_id or ""):
            return full
        from backend.application.cash_register.blind_count_visibility import (
            shift_has_open_blind_count,
        )
        reason = ("Importes ocultos: hay un arqueo ciego abierto en este turno"
                  if shift_has_open_blind_count(self._conn, shift_id)
                  else "Importes ocultos: el turno es de otro cajero")
        rows = tuple(LedgerRow(
            id=r.id, recorded_at=r.recorded_at, movement_type=r.movement_type,
            concept=r.concept, direction=r.direction, amount=None, balance=None,
            reversal_of_id=r.reversal_of_id, reference_id=r.reference_id,
            related_sale_id=r.related_sale_id, origin_label=r.origin_label,
            reversal_label=r.reversal_label) for r in full.rows)
        return LedgerProjection(shift_id, None, None, None, full.movement_count, rows, reason)

    def _sale_folios(self, sale_ids: set[str]) -> dict[str, str]:
        if not sale_ids or self._conn is None:
            return {}
        marks = ",".join("?" for _ in sale_ids)
        try:
            return {str(r[0]): str(r[1]) for r in self._conn.execute(
                f"SELECT id, sale_number FROM sales WHERE id IN ({marks})"
                " AND sale_number IS NOT NULL", tuple(sale_ids))}
        except Exception:  # noqa: BLE001 - base sin Ventas canónicas
            return {}

    def _full_projection(self, shift_id: str) -> LedgerProjection:
        balance = inflows = outflows = Decimal("0")
        rows: list[LedgerRow] = []
        items = list(self._reader.list_for_shift(shift_id))
        # Auditoría CJA-05: movimientos viejos con concepto «Venta <uuid>» se
        # muestran con el folio de la venta.
        folios = self._sale_folios(
            {str(i.get("reference_id") or "") for i in items}
            | {str(i.get("related_sale_id") or "") for i in items} - {""})
        by_id = {str(i["id"]): i for i in items}
        for item in items:
            amount = Decimal(item["amount"])
            if item["direction"] == "INFLOW":
                inflows += amount
                balance += amount
            else:
                outflows += amount
                balance -= amount
            rows.append(LedgerRow(
                id=item["id"], recorded_at=item["recorded_at"],
                movement_type=item["movement_type"],
                concept=_with_folio(item["concept"], item.get("reference_id"), folios),
                direction=item["direction"], amount=amount, balance=balance,
                reversal_of_id=item["reversal_of_id"],
                reference_id=item.get("reference_id"),
                related_sale_id=item.get("related_sale_id"),
                origin_label=_origin(item, folios, shift_id),
                reversal_label=_reversal(item, by_id)))
        return LedgerProjection(shift_id, balance, inflows, outflows, len(rows), tuple(rows))


def _with_folio(concept: str, reference_id: str | None, folios: dict[str, str]) -> str:
    folio = folios.get(str(reference_id or ""))
    if folio and reference_id and str(reference_id) in str(concept or ""):
        return str(concept).replace(str(reference_id), folio)
    return concept


def _origin(item: dict, folios: dict[str, str], shift_id: str) -> str:
    sale = str(item.get("related_sale_id") or "")
    reference = str(item.get("reference_id") or "")
    folio = folios.get(sale) or folios.get(reference)
    if folio:
        return f"{'Devolución de venta' if sale and item.get('direction') == 'OUTFLOW' else 'Venta'} {folio}"
    if reference and reference == shift_id:
        return "Apertura del turno"
    if not reference and not sale:
        return "Sin documento origen"
    return "Documento de Caja"


def _reversal(item: dict, by_id: dict[str, dict]) -> str:
    original = by_id.get(str(item.get("reversal_of_id") or ""))
    if original is None:
        return "Movimiento de otro turno" if item.get("reversal_of_id") else ""
    hour = str(original.get("recorded_at") or "")[11:16]
    return f"{original.get('concept') or 'Movimiento'} ({hour})" if hour else \
        str(original.get("concept") or "Movimiento")
