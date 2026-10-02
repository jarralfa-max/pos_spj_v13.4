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

import logging
import sqlite3

logger = logging.getLogger("spj.sales.folio")

DIGITS = 6
PREFIX = "V"


class SalesFolioClient:
    def __init__(self, connection) -> None:
        self._conn = connection

    def prefix_for(self, branch_id: str) -> str:
        try:
            fila = self._conn.execute(
                "SELECT code FROM branch_profiles WHERE branch_id=?", (branch_id,)).fetchone()
        except sqlite3.OperationalError:
            fila = None                         # sin perfiles de sucursal: sin código
        codigo = str(fila[0]).strip().upper() if fila and fila[0] else ""
        return f"{PREFIX}-{codigo}" if codigo else PREFIX

    def next_folio(self, branch_id: str) -> str | None:
        """El siguiente folio, o None si esta base no tiene el contador de
        documentos (una base de pruebas reducida; en la de la app lo crea la
        cadena de migraciones). Se registra en el log: nunca se inventa un
        número con `MAX()+1`."""
        try:
            return self._next_folio(branch_id)
        except sqlite3.OperationalError as exc:
            if "document_number_sequences" not in str(exc):
                raise
            logger.warning("Venta sin folio: no existe el contador de documentos (%s)", exc)
            return None

    def _next_folio(self, branch_id: str) -> str:
        from backend.domain.document_output.entities.document_number_sequence import (
            DocumentNumberSequence,
        )
        from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (  # noqa: E501
            SqliteDocumentNumberSequenceRepository,
        )

        prefijo = self.prefix_for(branch_id)
        repo = SqliteDocumentNumberSequenceRepository(self._conn)
        secuencia = repo.get_by_prefix(prefijo)
        if secuencia is None:
            secuencia = DocumentNumberSequence.create(prefix=prefijo)
            try:
                repo.save(secuencia)
            except sqlite3.IntegrityError:
                # Otra caja creó la secuencia al mismo tiempo: se usa la suya.
                secuencia = repo.get_by_prefix(prefijo)
        numero = repo.reserve_and_get(secuencia.id, period_key="")
        return f"{prefijo}-{numero:0{DIGITS}d}"
