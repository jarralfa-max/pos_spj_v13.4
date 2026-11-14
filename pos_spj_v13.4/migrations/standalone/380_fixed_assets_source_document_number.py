"""380 — Folio del documento de compra en el auxiliar de activos (SDLC-FIN-002).

Compras reconoce el costo de un activo y Finanzas lo da de alta en el auxiliar
ligado a ese documento. ``source_document_id`` guarda la identidad interna, pero
quien captura un alta manual escribe el FOLIO: sin él no se puede detectar que
esa factura ya se capitalizó, y el alta duplicaría la CxP o el pago.

Sólo agrega una columna nula. Idempotente.
"""

from __future__ import annotations


def run(conn) -> None:
    tiene_tabla = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                               " AND name='fixed_assets'").fetchone()
    if tiene_tabla is None:
        return  # base sin Finanzas: el DDL born-clean ya trae la columna
    columnas = {str(r[1]) for r in conn.execute("PRAGMA table_info(fixed_assets)")}
    if "source_document_number" not in columnas:
        conn.execute("ALTER TABLE fixed_assets ADD COLUMN source_document_number TEXT")


up = run
