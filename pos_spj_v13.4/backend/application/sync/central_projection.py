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


# ── ciclo de proyección ──────────────────────────────────────────────────────
class CentralProjectionRepository(Protocol):
    def pending_facts(self, *, projector: str, limit: int) -> list[Mapping[str, Any]]: ...
    def savepoint(self): ...
    def log(self, *, event_id: str, projector: str, status: str, error: str | None) -> None: ...
    def upsert_sale(self, rows: dict) -> None: ...
    def set_sale_status(self, *, sale_id: str, status: str, event_id: str) -> None: ...
    def add_sale_return(self, row: dict) -> None: ...
    def add_stock_movement(self, rows: dict) -> None: ...
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
        }

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
           "ProjectionRun", "sale_return_row", "sale_rows", "stock_rows"]
