"""SalesFolioClient — el folio comercial de una venta (§6: Ventas es dueña del
"folio comercial").

Hasta la re-auditoría POS (2026-10-01) `sales.sale_number` existía en el
esquema y en el agregado pero NADIE lo asignaba: el ticket imprimía los
últimos 8 caracteres del UUID y no había número con el que buscar una venta
para devolverla o reimprimirla.

Mismo mecanismo que el folio de Procesamiento (`ProcessingOrderFolioAdapter`):
el contador seguro del sistema (`document_number_sequences`, un `UPDATE ...
RETURNING` atómico, uno por prefijo, sin reinicio) con prefijo
``V-<código de sucursal>``. Se reserva en la MISMA transacción del cobro: si
el cobro no se confirma, el consecutivo tampoco avanza.

Sin código de sucursal (Configuración → Empresa y sucursales) el prefijo es
``V`` a secas, en vez de impedir la venta: un mostrador no se detiene por un
dato de configuración. Al registrar el código, la numeración sigue en su
propio prefijo.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.document_output.branch_document_folio import (
    DIGITS,
    branch_folio_prefix,
    next_branch_folio,
)

__all__ = ["DIGITS", "PREFIX", "SalesFolioClient"]

PREFIX = "V"


class SalesFolioClient:
    """Folio ``V-<código>-000001``; la mecánica vive en `branch_document_folio`
    (compartida con los Cortes X/Z de Caja)."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def prefix_for(self, branch_id: str) -> str:
        return branch_folio_prefix(self._conn, PREFIX, branch_id)

    def next_folio(self, branch_id: str) -> str | None:
        return next_branch_folio(self._conn, PREFIX, branch_id)
