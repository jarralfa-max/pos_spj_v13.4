"""Folio consecutivo por sucursal: ``<TIPO>-<código de sucursal>-000001``.

Una sola implementación para todo documento comercial numerado por sucursal
(venta ``V``, Corte X ``X``, Corte Z ``Z``): el contador seguro del sistema
(`document_number_sequences`, un ``UPDATE ... RETURNING`` atómico, uno por
prefijo, sin reinicio). Se reserva en la transacción del llamador: si la
operación no se confirma, el consecutivo tampoco avanza.

Sin código de sucursal (Configuración → Empresa y sucursales) el prefijo es el
tipo a secas, en vez de impedir la operación. Al registrar el código, la
numeración sigue en su propio prefijo.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.document_output.folio")

DIGITS = 6


def branch_folio_prefix(connection, kind: str, branch_id: str) -> str:
    try:
        fila = connection.execute(
            "SELECT code FROM branch_profiles WHERE branch_id=?", (branch_id,)).fetchone()
    except sqlite3.OperationalError:
        fila = None                             # sin perfiles de sucursal: sin código
    codigo = str(fila[0]).strip().upper() if fila and fila[0] else ""
    return f"{kind}-{codigo}" if codigo else kind


def next_branch_folio(connection, kind: str, branch_id: str) -> str | None:
    """El siguiente folio, o None si esta base no tiene el contador de documentos
    (una base de pruebas reducida; en la de la app lo crea la cadena de
    migraciones). Se registra en el log: nunca se inventa un número con
    ``MAX()+1``."""
    try:
        return _next(connection, kind, branch_id)
    except sqlite3.OperationalError as exc:
        if "document_number_sequences" not in str(exc):
            raise
        logger.warning("Documento %s sin folio: no existe el contador de documentos (%s)",
                       kind, exc)
        return None


def _next(connection, kind: str, branch_id: str) -> str:
    from backend.domain.document_output.entities.document_number_sequence import (
        DocumentNumberSequence,
    )
    from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (  # noqa: E501
        SqliteDocumentNumberSequenceRepository,
    )

    prefijo = branch_folio_prefix(connection, kind, branch_id)
    repo = SqliteDocumentNumberSequenceRepository(connection)
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
