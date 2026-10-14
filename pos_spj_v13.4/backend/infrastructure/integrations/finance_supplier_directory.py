"""Maestro de proveedores visto desde Finanzas (auditoría d9f2bca F13).

Antes un pago se programaba y ejecutaba contra cualquier UUID: nadie
comprobaba que el beneficiario existiera, estuviera activo o no tuviera
bloqueados los pagos. Este adaptador lee el maestro canónico (``proveedores``,
el mismo que usa Compras desde la migración 263) y responde, falla cerrada,
si se le puede pagar y con qué datos bancarios.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierPaymentEligibility:
    eligible: bool
    reason: str = ""
    name: str = ""
    bank_account: str = ""


class SqliteSupplierDirectory:
    def __init__(self, connection) -> None:
        self._conn = connection

    def payment_eligibility(self, supplier_id: str) -> SupplierPaymentEligibility:
        if not self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='proveedores'"
        ).fetchone():
            return SupplierPaymentEligibility(
                False, "No hay maestro de proveedores para validar al beneficiario")
        columns = {str(r[1]) for r in self._conn.execute("PRAGMA table_info(proveedores)")}
        select = ["nombre", "activo"]
        for optional in ("bloqueado_financiero", "motivo_bloqueo", "cuenta_bancaria"):
            if optional in columns:
                select.append(optional)
        row = self._conn.execute(
            f"SELECT {', '.join(select)} FROM proveedores WHERE id=?", (str(supplier_id),)
        ).fetchone()
        if row is None:
            return SupplierPaymentEligibility(
                False, "El proveedor no existe en el maestro de proveedores")
        data = dict(zip(select, row))
        name = str(data.get("nombre") or "")
        if not int(data.get("activo") or 0):
            return SupplierPaymentEligibility(False, f"El proveedor {name} está dado de baja",
                                              name=name)
        if int(data.get("bloqueado_financiero") or 0):
            motivo = str(data.get("motivo_bloqueo") or "").strip()
            return SupplierPaymentEligibility(
                False, f"El proveedor {name} tiene los pagos bloqueados"
                       + (f": {motivo}" if motivo else ""), name=name)
        return SupplierPaymentEligibility(
            True, name=name, bank_account=str(data.get("cuenta_bancaria") or "").strip())
