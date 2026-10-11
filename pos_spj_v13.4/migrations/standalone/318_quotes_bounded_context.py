"""318 — Cotizaciones como contexto propio (CRM-43, 2026-10-09).

POR QUÉ HACE FALTA (medido en una copia de la base viva)
-------------------------------------------------------
No existía un módulo de cotizaciones: los casos de uso ``create_quote_use_case``
y afines eran cascarones sin manejador ni llamadores, y la tabla legacy
``cotizaciones`` (identidad ``cliente_id`` de ``clientes``) no tenía escritor
(0 filas). Pedidos ya preveía la conversión (tipo ``QUOTE_CONVERTED`` y campo
``customer_orders.quote_id``) sin que nada la produjera.

QUÉ HACE
--------
* Crea ``quotes``, ``quote_lines``, ``quote_audit_log`` y ``quote_outbox``
  (``backend/infrastructure/db/schema/quotes_schema.py``).
* Copia las filas de ``cotizaciones``/``cotizaciones_detalle`` que hubiera, con
  el cliente canónico (``customers.legacy_customer_id``); una cotización sin
  cliente canónico se omite y se registra en el log. Idempotente por
  ``legacy_quote_id``. La tabla legacy no se borra.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from backend.infrastructure.db.schema.quotes_schema import create_quotes_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.318")

_STATUS = {"pendiente": "SENT", "aprobada": "ACCEPTED", "rechazada": "REJECTED",
           "vencida": "EXPIRED", "convertida": "CONVERTED"}


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def _dec(value) -> str:
    try:
        return str(Decimal(str(value if value is not None else 0)).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "0.00"


def _copiar_legacy(conn) -> tuple[int, int]:
    if not (_tabla(conn, "cotizaciones") and _tabla(conn, "customers")):
        return 0, 0
    copiadas = omitidas = 0
    filas = conn.execute(
        "SELECT q.id, q.folio, q.cliente_id, q.subtotal, q.descuento, q.total, q.estado,"
        " q.notas, q.fecha_vencimiento, q.usuario, q.sucursal_id, q.fecha,"
        " (SELECT c.id FROM customers c WHERE c.legacy_customer_id = q.cliente_id)"
        " FROM cotizaciones q WHERE NOT EXISTS"
        " (SELECT 1 FROM quotes n WHERE n.legacy_quote_id = q.id)").fetchall()
    ultimo = conn.execute("SELECT MAX(CAST(SUBSTR(quote_number, 5) AS INTEGER)) FROM quotes"
                          " WHERE quote_number LIKE 'COT-%'").fetchone()[0] or 0
    for (legacy_id, folio, _cliente, subtotal, descuento, total, estado, notas, vence,
         usuario, sucursal, fecha, customer_id) in filas:
        if not customer_id:
            omitidas += 1
            logger.warning("318: cotización legacy %s sin cliente canónico; se omite.",
                           legacy_id)
            continue
        ultimo += 1
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        creada = str(fecha or ahora)
        quote_id = new_uuid()
        nota = (notas or "") + (f"\nFolio anterior: {folio}" if folio else "")
        conn.execute(
            "INSERT INTO quotes (id, quote_number, customer_id, branch_id, status, valid_until,"
            " notes, list_subtotal, discount_total, total, created_by_user_id, legacy_quote_id,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (quote_id, f"COT-{ultimo:06d}", customer_id, sucursal or "",
             _STATUS.get(str(estado or "").lower(), "SENT"),
             str(vence or date.fromisoformat(creada[:10]).isoformat())[:10], nota.strip(),
             _dec(subtotal), _dec(descuento), _dec(total), str(usuario or "legacy"), legacy_id,
             creada, ahora))
        if _tabla(conn, "cotizaciones_detalle"):
            detalle = conn.execute(
                "SELECT producto_id, nombre, cantidad, unidad, precio_unitario, subtotal"
                " FROM cotizaciones_detalle WHERE cotizacion_id=?", (legacy_id,)).fetchall()
            for n, (producto, nombre, cantidad, unidad, precio, importe) in enumerate(detalle, 1):
                conn.execute(
                    "INSERT INTO quote_lines (id, quote_id, line_number, product_id,"
                    " description, unit_code, quantity, list_price, unit_price, line_total)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (new_uuid(), quote_id, n, producto or "", nombre or "", unidad or "",
                     str(cantidad or 0), _dec(precio), _dec(precio), _dec(importe)))
        copiadas += 1
    return copiadas, omitidas


def run(conn) -> None:
    create_quotes_schema(conn)
    copiadas, omitidas = _copiar_legacy(conn)
    conn.commit()
    logger.info("318: esquema de cotizaciones listo; legacy copiadas=%s omitidas=%s",
                copiadas, omitidas)


up = run
