"""Proyecciones centrales de Ventas e Inventario (arquitectura híbrida, Slice 5).

El servidor central NO recalcula reglas de negocio: proyecta lo que la estación
ya decidió y dejó en el libro de hechos.

* `SALE_COMPLETED` → venta con totales, renglones y pagos tal como la cerró la caja.
* `SALE_CANCELLED` / `SALE_REVERSED` → cambia el estado de la venta (si existe).
* `SALE_RETURNED` → una devolución con su importe.
* `INVENTORY_MOVEMENT_POSTED` / `INVENTORY_MOVEMENT_REVERSED` → el movimiento con
  los efectos EXACTOS que aplicó a los saldos de la estación (Slice 5 los agregó
  al evento). La existencia central es la suma de esos efectos.

Cada hecho se proyecta UNA vez (registro por hecho y proyector); un hecho que
falla queda en ERROR con su motivo y no traba a los siguientes. Los traductores
de abajo son funciones puras (hecho → renglones): se prueban sin base.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Protocol

logger = logging.getLogger("spj.sync.projection")

PROJECTOR = "central_v1"


class ProjectionError(ValueError):
    """El hecho no trae lo que la proyección necesita."""


def _dec(valor: Any, campo: str) -> Decimal:
    if isinstance(valor, float):
        raise ProjectionError(f"{campo} llegó como float")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ProjectionError(f"{campo} no es un número exacto: {valor!r}") from exc
    if not numero.is_finite():
        raise ProjectionError(f"{campo} no es finito")
    return numero


def _opt_dec(valor: Any, campo: str) -> Decimal | None:
    return None if valor in (None, "") else _dec(valor, campo)


# ── traductores puros ────────────────────────────────────────────────────────
def sale_rows(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    try:
        venta = {
            "sale_id": p.get("sale_id") or fact["aggregate_id"],
            "event_id": fact["event_id"], "branch_id": fact["branch_id"],
            "station_id": fact["station_id"], "folio": str(p.get("folio") or ""),
            "customer_id": p.get("customer_id") or None,
            "channel": str(p.get("channel") or "POS"),
            "currency_code": str(p.get("currency_code") or "MXN"),
            "occurred_at": fact["occurred_at"],
            **{campo: _dec(p.get(campo, "0"), campo) for campo in (
                "gross_subtotal", "discount_total", "promotion_total", "coupon_total",
                "loyalty_total", "tax_total", "rounding_adjustment", "total")},
            "change_given": _dec(p.get("change", "0"), "change"),
        }
    except KeyError as exc:
        raise ProjectionError(f"Falta {exc} en SALE_COMPLETED") from exc
    renglones = [{"line_no": i, "product_id": l["product_id"],
                  "quantity": _dec(l["quantity"], "quantity"),
                  "amount": _dec(l["amount"], "amount"),
                  "unit_cost": _opt_dec(l.get("unit_cost"), "unit_cost")}
                 for i, l in enumerate(p.get("lines") or [], start=1)]
    pagos: dict[str, Decimal] = {}
    for pago in p.get("payments") or []:
        pagos[str(pago["method"])] = pagos.get(str(pago["method"]), Decimal("0")) + _dec(
            pago["amount"], "payment.amount")
    return {"sale": venta, "lines": renglones,
            "payments": [{"method": m, "amount": a} for m, a in sorted(pagos.items())]}


def sale_return_row(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    importe = p.get("amount", p.get("refunded_total"))
    if importe in (None, ""):
        raise ProjectionError("SALE_RETURNED sin importe")
    return {"event_id": fact["event_id"], "sale_id": fact["aggregate_id"],
            "branch_id": fact["branch_id"], "amount": _dec(importe, "amount"),
            "occurred_at": fact["occurred_at"]}


def stock_rows(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    if "effects" not in p:
        # Eventos emitidos antes del Slice 5 no traen efectos: no se inventan.
        raise ProjectionError("Movimiento sin efectos (anterior al Slice 5)")
    reversa = fact["event_type"] == "INVENTORY_MOVEMENT_REVERSED"
    movimiento = {
        "movement_id": fact["aggregate_id"], "event_id": fact["event_id"],
        "branch_id": fact["branch_id"],
        "warehouse_id": p.get("warehouse_id"),
        "movement_type": "REVERSAL" if reversa else str(p.get("movement_type") or ""),
        "document_module": p.get("document_module"),
        "document_type": "REVERSAL" if reversa else p.get("source_document_type"),
        "document_id": p.get("reversal_of_id") if reversa else p.get("source_document_id"),
        "reversal_of_id": p.get("reversal_of_id") if reversa else None,
        "occurred_at": p.get("occurred_at") or fact["occurred_at"],
    }
    if not movimiento["warehouse_id"] or not movimiento["movement_type"]:
        raise ProjectionError("Movimiento sin almacén o sin tipo")
    efectos = [{"effect_no": i, "product_id": e["product_id"], "lot_id": e.get("lot_id"),
                "warehouse_id": e.get("warehouse_id") or movimiento["warehouse_id"],
                "location_id": e.get("location_id"),
                "inventory_status": str(e.get("inventory_status") or "AVAILABLE"),
                "quantity_delta": _dec(e.get("quantity_delta", "0"), "quantity_delta"),
                "weight_delta": _dec(e.get("weight_delta", "0"), "weight_delta")}
               for i, e in enumerate(p["effects"], start=1)]
    return {"movement": movimiento, "effects": efectos}


# ── Caja (Slice 6) ───────────────────────────────────────────────────────────
_INFLOW = {"INFLOW", "IN", "ENTRADA"}
_OUTFLOW = {"OUTFLOW", "OUT", "SALIDA"}


def cash_shift_row(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    if "opening_amount" not in p:
        raise ProjectionError("CASH_SHIFT_OPENED sin monto de apertura")
    return {"shift_id": fact["aggregate_id"], "event_id": fact["event_id"],
            "branch_id": fact["branch_id"], "station_id": fact["station_id"],
            "register_id": p.get("register_id"), "cashier_user_id": p.get("cashier_user_id"),
            "opening_amount": _dec(p["opening_amount"], "opening_amount"),
            "opened_at": fact["occurred_at"]}


def cash_movement_row(fact: Mapping[str, Any]) -> dict:
    """Movimiento de caja con importe FIRMADO desde el cajón: entrada +, salida −.
    Un retiro a caja fuerte sale del cajón."""
    p = fact["payload"]
    importe = _dec(p.get("amount"), "amount")
    if fact["event_type"] == "CASH_SAFE_DROP_RECORDED":
        tipo, signo = "SAFE_DROP", Decimal("-1")
    else:
        direccion = str(p.get("direction") or "").upper()
        if direccion in _INFLOW:
            signo = Decimal("1")
        elif direccion in _OUTFLOW:
            signo = Decimal("-1")
        else:
            raise ProjectionError(f"Movimiento de caja sin dirección: {direccion!r}")
        tipo = str(p.get("movement_type") or "MOVEMENT")
    return {"movement_id": fact["aggregate_id"], "event_id": fact["event_id"],
            "branch_id": fact["branch_id"], "shift_id": p.get("shift_id"),
            "movement_kind": tipo, "signed_amount": signo * abs(importe),
            "reversal_of_id": None, "sale_id": p.get("sale_id"),
            "occurred_at": fact["occurred_at"]}


def cash_reversal_row(fact: Mapping[str, Any], original_signed: Decimal | None) -> dict:
    p = fact["payload"]
    if original_signed is None:
        raise ProjectionError("La reversa llegó antes que su movimiento original")
    importe = abs(_dec(p.get("amount"), "amount"))
    signo = Decimal("-1") if original_signed > 0 else Decimal("1")
    return {"movement_id": fact["aggregate_id"], "event_id": fact["event_id"],
            "branch_id": fact["branch_id"], "shift_id": p.get("shift_id"),
            "movement_kind": "REVERSAL", "signed_amount": signo * importe,
            "reversal_of_id": p.get("reversal_of_id"), "sale_id": p.get("sale_id"),
            "occurred_at": fact["occurred_at"]}


def cash_cut_row(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    try:
        return {"cut_id": fact["aggregate_id"], "event_id": fact["event_id"],
                "branch_id": fact["branch_id"], "shift_id": p["shift_id"],
                "document_number": str(p.get("document_number") or ""),
                "expected_cash": _dec(p["expected_cash"], "expected_cash"),
                "counted_cash": _dec(p["counted_cash"], "counted_cash"),
                "difference": _dec(p["difference"], "difference"),
                "business_date": p.get("business_date") or None,
                "occurred_at": fact["occurred_at"]}
    except KeyError as exc:
        raise ProjectionError(f"Corte Z sin {exc}") from exc


# ── Finanzas (Slice 6) ───────────────────────────────────────────────────────
def journal_rows(fact: Mapping[str, Any]) -> dict:
    """Asiento con renglones. Si no cuadra (debe ≠ haber) o no coincide con sus
    totales, NO se proyecta: nunca se corrige un asiento en silencio."""
    p = fact["payload"]
    if not p.get("lines"):
        raise ProjectionError("Asiento sin renglones (anterior al Slice 6)")
    renglones = [{"line_index": int(l.get("line_index", i)),
                  "account_code": str(l.get("account_code") or ""),
                  "account_type": l.get("account_type"),
                  "is_receivable": bool(l.get("is_receivable")),
                  "debit": _dec(l.get("debit", "0"), "debit"),
                  "credit": _dec(l.get("credit", "0"), "credit"),
                  "line_role": l.get("line_role"), "line_branch_id": l.get("branch_id"),
                  "cost_center_id": l.get("cost_center_id"), "customer_id": l.get("customer_id"),
                  "supplier_id": l.get("supplier_id"), "product_id": l.get("product_id")}
                 for i, l in enumerate(p["lines"])]
    if any(not r["account_code"] for r in renglones):
        raise ProjectionError("Renglón sin código de cuenta")
    cargos = sum((r["debit"] for r in renglones), Decimal("0"))
    abonos = sum((r["credit"] for r in renglones), Decimal("0"))
    if cargos != abonos:
        raise ProjectionError(f"ASIENTO_DESCUADRADO: cargos {cargos} ≠ abonos {abonos}")
    total_d = _dec(p.get("total_debits", cargos), "total_debits")
    total_c = _dec(p.get("total_credits", abonos), "total_credits")
    if (total_d, total_c) != (cargos, abonos):
        raise ProjectionError("Los renglones no suman los totales del asiento")
    asiento = {"entry_id": p.get("journal_entry_id") or fact["aggregate_id"],
               "event_id": fact["event_id"], "branch_id": p.get("branch_id") or fact["branch_id"],
               "entry_number": str(p.get("entry_number") or ""),
               "entry_date": p.get("entry_date"), "posting_date": p.get("posting_date"),
               "source_module": p.get("source_module"),
               "source_document_ref": p.get("source_document_id"),
               "posting_purpose": p.get("posting_purpose"),
               "currency_code": str(p.get("currency_code") or "MXN"),
               "base_currency_code": str(p.get("base_currency_code") or "MXN"),
               "total_debits": total_d, "total_credits": total_c,
               "reversal_of_entry_id": p.get("reversal_of_entry_id"),
               "occurred_at": fact["occurred_at"]}
    if not asiento["entry_date"] or not asiento["posting_date"]:
        raise ProjectionError("Asiento sin fechas")
    return {"entry": asiento, "lines": renglones}


# ── Crédito (Slice 6) ────────────────────────────────────────────────────────
_CREDIT_STATUS = {
    "CUSTOMER_CREDIT_APPROVED": "ACTIVE", "CUSTOMER_CREDIT_REOPENED": "ACTIVE",
    "CUSTOMER_CREDIT_SUSPENDED": "SUSPENDED", "CUSTOMER_CREDIT_BLOCKED": "BLOCKED",
    "CUSTOMER_CREDIT_CLOSED": "CLOSED", "CUSTOMER_CREDIT_REJECTED": "REJECTED",
    "CUSTOMER_CREDIT_LIMIT_UPDATED": None, "CUSTOMER_CREDIT_LIMIT_OVERRIDDEN": None,
}


def credit_account_row(fact: Mapping[str, Any]) -> dict:
    p = fact["payload"]
    if not p.get("profile_id") or not p.get("customer_id"):
        raise ProjectionError("Evento de crédito sin cliente o sin perfil")
    limite = p.get("credit_limit", p.get("new_limit"))
    return {"profile_id": p["profile_id"], "customer_id": p["customer_id"],
            "branch_id": fact["branch_id"], "status": _CREDIT_STATUS[fact["event_type"]],
            "credit_limit": _opt_dec(limite, "credit_limit"),
            "event_id": fact["event_id"], "occurred_at": fact["occurred_at"]}


# ── Fidelidad (Slice 6) ──────────────────────────────────────────────────────
def loyalty_transaction_row(fact: Mapping[str, Any]) -> dict:
    libro = fact["payload"].get("ledger")
    if not libro or not libro.get("transaction_id"):
        raise ProjectionError("Evento de puntos sin datos del libro (anterior al Slice 6)")
    return {"transaction_id": libro["transaction_id"], "event_id": fact["event_id"],
            "loyalty_account_id": libro["loyalty_account_id"],
            "customer_id": libro.get("customer_id"), "membership_id": libro.get("membership_id"),
            "branch_id": fact["branch_id"],
            "transaction_type": str(libro.get("transaction_type") or ""),
            "status": str(libro.get("status") or ""),
            "points_amount": _dec(libro.get("points_amount"), "points_amount"),
            "counts_toward_balance": bool(libro.get("counts_toward_balance")),
            "sale_id": libro.get("sale_id"), "occurred_at": fact["occurred_at"]}


_LOYALTY_LEDGER = ("LOYALTY_POINTS_ISSUED", "LOYALTY_POINTS_RESERVED", "LOYALTY_POINTS_REDEEMED",
                   "LOYALTY_POINTS_RELEASED", "LOYALTY_POINTS_EXPIRED", "LOYALTY_POINTS_ADJUSTED",
                   "LOYALTY_TRANSACTION_REVERSED")


# ── ciclo de proyección ──────────────────────────────────────────────────────
class CentralProjectionRepository(Protocol):
    def pending_facts(self, *, projector: str, limit: int) -> list[Mapping[str, Any]]: ...
    def savepoint(self): ...
    def log(self, *, event_id: str, projector: str, status: str, error: str | None) -> None: ...
    def upsert_sale(self, rows: dict) -> None: ...
    def set_sale_status(self, *, sale_id: str, status: str, event_id: str) -> None: ...
    def add_sale_return(self, row: dict) -> None: ...
    def add_stock_movement(self, rows: dict) -> None: ...
    def open_cash_shift(self, row: dict) -> None: ...
    def close_cash_shift(self, *, shift_id: str, closed_at: Any, z_cut_id: str | None) -> None: ...
    def add_cash_movement(self, row: dict) -> None: ...
    def cash_movement_signed(self, movement_id: str) -> Decimal | None: ...
    def add_cash_cut(self, row: dict) -> None: ...
    def add_journal_entry(self, rows: dict) -> None: ...
    def upsert_credit_account(self, row: dict) -> None: ...
    def upsert_loyalty_transaction(self, row: dict) -> None: ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class ProjectionRun:
    projected: int
    skipped: int
    errors: int


class CentralProjector:
    def __init__(self, repository: CentralProjectionRepository) -> None:
        self._repo = repository
        self._handlers: dict[str, Callable[[Mapping[str, Any]], None]] = {
            "SALE_COMPLETED": lambda f: self._repo.upsert_sale(sale_rows(f)),
            "SALE_CANCELLED": lambda f: self._repo.set_sale_status(
                sale_id=f["aggregate_id"], status="CANCELLED", event_id=f["event_id"]),
            "SALE_REVERSED": lambda f: self._repo.set_sale_status(
                sale_id=f["aggregate_id"], status="REVERSED", event_id=f["event_id"]),
            "SALE_RETURNED": lambda f: self._repo.add_sale_return(sale_return_row(f)),
            "INVENTORY_MOVEMENT_POSTED": lambda f: self._repo.add_stock_movement(stock_rows(f)),
            "INVENTORY_MOVEMENT_REVERSED": lambda f: self._repo.add_stock_movement(stock_rows(f)),
            # Slice 6
            "CASH_SHIFT_OPENED": lambda f: self._repo.open_cash_shift(cash_shift_row(f)),
            "CASH_SHIFT_CLOSED": self._close_shift,
            "CASH_SHIFT_FORCE_CLOSED": self._close_shift,
            "CASH_MOVEMENT_RECORDED": lambda f: self._repo.add_cash_movement(cash_movement_row(f)),
            "CASH_SAFE_DROP_RECORDED": lambda f: self._repo.add_cash_movement(cash_movement_row(f)),
            "CASH_MOVEMENT_REVERSED": lambda f: self._repo.add_cash_movement(cash_reversal_row(
                f, self._repo.cash_movement_signed(str(f["payload"].get("reversal_of_id"))))),
            "CASH_Z_CUT_GENERATED": lambda f: self._repo.add_cash_cut(cash_cut_row(f)),
            "JOURNAL_ENTRY_POSTED": lambda f: self._repo.add_journal_entry(journal_rows(f)),
            "JOURNAL_ENTRY_REVERSED": lambda f: self._repo.add_journal_entry(journal_rows(f)),
            **{evento: (lambda f: self._repo.upsert_credit_account(credit_account_row(f)))
               for evento in _CREDIT_STATUS},
            **{evento: (lambda f: self._repo.upsert_loyalty_transaction(
                loyalty_transaction_row(f))) for evento in _LOYALTY_LEDGER},
        }

    def _close_shift(self, fact) -> None:
        p = fact["payload"]
        self._repo.close_cash_shift(shift_id=p.get("shift_id") or fact["aggregate_id"],
                                    closed_at=p.get("closed_at") or fact["occurred_at"],
                                    z_cut_id=p.get("z_cut_id"))

    def run_once(self, *, limit: int = 500) -> ProjectionRun:
        hechos = proyectados = saltados = errores = 0
        for hecho in self._repo.pending_facts(projector=PROJECTOR, limit=limit):
            hechos += 1
            manejador = self._handlers.get(hecho["event_type"])
            if manejador is None:
                self._repo.log(event_id=hecho["event_id"], projector=PROJECTOR,
                               status="SKIPPED", error=None)
                saltados += 1
                continue
            try:
                with self._repo.savepoint():
                    manejador(hecho)
                    self._repo.log(event_id=hecho["event_id"], projector=PROJECTOR,
                                   status="OK", error=None)
                proyectados += 1
            except Exception as exc:   # visible y sin trabar a los siguientes
                logger.warning("proyección: %s %s falló: %s", hecho["event_type"],
                               hecho["event_id"], exc)
                self._repo.log(event_id=hecho["event_id"], projector=PROJECTOR,
                               status="ERROR", error=f"{type(exc).__name__}: {exc}"[:500])
                errores += 1
        self._repo.commit()
        return ProjectionRun(proyectados, saltados, errores)


__all__ = ["CentralProjectionRepository", "CentralProjector", "PROJECTOR", "ProjectionError",
           "ProjectionRun", "cash_cut_row", "cash_movement_row", "cash_reversal_row",
           "cash_shift_row", "credit_account_row", "journal_rows", "loyalty_transaction_row",
           "sale_return_row", "sale_rows", "stock_rows"]
