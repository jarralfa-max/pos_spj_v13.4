"""Días de crédito del proveedor, leídos de sus condiciones comerciales.

Implementa `SupplierPaymentTermsPort` sobre la consulta del contexto de
Proveedores (`SupplierDetailQueryService.commercial_terms`), la misma que
alimenta la pestaña "Condiciones" de la ficha. Compras no lee la tabla
`supplier_commercial_terms` directamente.

Contado (`is_credit` falso) o sin condiciones -> 0 días: la cuenta por pagar
vence el mismo día (decisión del usuario, 2026-09-18).
"""

from __future__ import annotations

import sqlite3


class SupplierPaymentTermsAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def credit_days(self, supplier_id: str) -> int:
        from backend.application.suppliers.queries.supplier_read_services import (
            SupplierDetailQueryService,
        )
        try:
            terms = SupplierDetailQueryService(self._connection).commercial_terms(supplier_id)
        except sqlite3.OperationalError:
            return 0
        if not terms or not terms.get("is_credit"):
            return 0
        try:
            return max(0, int(terms.get("credit_days") or 0))
        except (TypeError, ValueError):
            return 0
