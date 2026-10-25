"""Puntos de ventas a crédito pendientes de cobro (auditoría 968e0bc FID-04)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LoyaltyDeferredAccrualRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def schema_ready(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='loyalty_deferred_accruals'").fetchone() is not None

    def get(self, sale_id: str) -> dict | None:
        fila = self._conn.execute(
            "SELECT sale_id, customer_id, loyalty_account_id, branch_id, credit_amount,"
            " deferred_points, collected_amount, accrued_points, status"
            " FROM loyalty_deferred_accruals WHERE sale_id=?", (sale_id,)).fetchone()
        if fila is None:
            return None
        claves = ("sale_id", "customer_id", "loyalty_account_id", "branch_id",
                  "credit_amount", "deferred_points", "collected_amount", "accrued_points",
                  "status")
        datos = dict(zip(claves, tuple(fila)))
        for clave in ("credit_amount", "deferred_points", "collected_amount", "accrued_points"):
            datos[clave] = Decimal(str(datos[clave]))
        return datos

    def open(self, *, sale_id: str, customer_id: str, loyalty_account_id: str | None,
             branch_id: str | None, credit_amount: Decimal, deferred_points: int) -> None:
        ahora = _now()
        self._conn.execute(
            "INSERT OR IGNORE INTO loyalty_deferred_accruals (sale_id, customer_id,"
            " loyalty_account_id, branch_id, credit_amount, deferred_points, created_at,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (sale_id, customer_id, loyalty_account_id, branch_id, str(credit_amount),
             str(int(deferred_points)), ahora, ahora))

    def has_collection(self, application_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM loyalty_deferred_accrual_collections WHERE application_id=?",
            (application_id,)).fetchone() is not None

    def record_collection(self, *, application_id: str, sale_id: str, amount: Decimal,
                          points: int, collected_total: Decimal, accrued_total: int,
                          closed: bool) -> None:
        ahora = _now()
        self._conn.execute(
            "INSERT INTO loyalty_deferred_accrual_collections (application_id, sale_id,"
            " amount, points, created_at) VALUES (?,?,?,?,?)",
            (application_id, sale_id, str(amount), str(int(points)), ahora))
        self._conn.execute(
            "UPDATE loyalty_deferred_accruals SET collected_amount=?, accrued_points=?,"
            " status=?, updated_at=? WHERE sale_id=?",
            (str(collected_total), str(int(accrued_total)), "CLOSED" if closed else "OPEN",
             ahora, sale_id))

    def scale(self, sale_id: str, factor: Decimal) -> None:
        """Una devolución parcial reduce lo que falta por acreditar."""
        fila = self.get(sale_id)
        if fila is None or fila["status"] != "OPEN":
            return
        from decimal import ROUND_DOWN
        nuevos = (fila["deferred_points"] * factor).to_integral_value(rounding=ROUND_DOWN)
        self._conn.execute(
            "UPDATE loyalty_deferred_accruals SET deferred_points=?, credit_amount=?,"
            " updated_at=? WHERE sale_id=?",
            (str(max(nuevos, fila["accrued_points"])),
             str((fila["credit_amount"] * factor).quantize(Decimal("0.01"))), _now(), sale_id))

    def cancel(self, sale_id: str) -> None:
        self._conn.execute(
            "UPDATE loyalty_deferred_accruals SET status='CANCELLED', updated_at=?"
            " WHERE sale_id=? AND status='OPEN'", (_now(), sale_id))

    def sale_of_receivable(self, receivable_id: str) -> str | None:
        """La venta que originó la CxC (documento de Finanzas con origen «sales»)."""
        try:
            fila = self._conn.execute(
                "SELECT d.source_document_id FROM receivables r"
                " JOIN financial_documents d ON d.id = r.financial_document_id"
                " WHERE r.id=? AND d.source_module='sales'", (receivable_id,)).fetchone()
        except Exception:  # noqa: BLE001 - sin Finanzas instalada no hay CxC
            return None
        return str(fila[0]) if fila and fila[0] else None
