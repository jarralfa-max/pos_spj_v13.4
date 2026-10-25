"""Maestro de proveedores visto desde Finanzas (auditoría d9f2bca F13).

Lee el maestro canónico (``proveedores``, el mismo que usa Compras desde la
migración 263) y responde, falla cerrada, si se le puede pagar a un proveedor
y con qué cuenta bancaria. Implementa ``SupplierDirectoryPort``.
"""

from __future__ import annotations

from backend.application.finance.ports import SupplierPaymentEligibility


class SqliteSupplierDirectory:
    def __init__(self, connection) -> None:
        self._conn = connection

    def payment_eligibility(self, supplier_id: str) -> SupplierPaymentEligibility:
        row = self._conn.execute(
            "SELECT nombre, activo, bloqueado_financiero, motivo_bloqueo, cuenta_bancaria"
            " FROM proveedores WHERE id=?", (str(supplier_id),)).fetchone()
        if row is None:
            return SupplierPaymentEligibility(
                False, "El proveedor no existe en el maestro de proveedores")
        name, active, blocked, block_reason, bank_account = row
        name = str(name or "")
        if not int(active or 0):
            return SupplierPaymentEligibility(False, f"El proveedor {name} está dado de baja",
                                              name=name)
        if int(blocked or 0):
            motivo = str(block_reason or "").strip()
            return SupplierPaymentEligibility(
                False, f"El proveedor {name} tiene los pagos bloqueados"
                       + (f": {motivo}" if motivo else ""), name=name)
        return SupplierPaymentEligibility(True, name=name,
                                          bank_account=str(bank_account or "").strip())
