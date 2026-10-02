# migrations/standalone/280_compra_en_origen_supplier_origin.py
"""280 — Compra en origen de punta a punta (Compras FASE 8-11).

* ``supplier_addresses.label``: el nombre con que se reconoce una bodega o punto de
  recolección ("Bodega Norte"). `supplier_schema.py` no tiene mecanismo de ALTER:
  la columna nace en el DDL y aquí se agrega a las bases existentes.
* ``logistics_shipments``: origen por dirección del proveedor
  (``origin_supplier_address_id`` + ``origin_address_snapshot``) y las marcas de
  tránsito/recepción. El esquema de Logística vive en la 171 (DDL "born clean");
  las bases existentes reciben las columnas aquí.
* ``logistics_arrival_counts``: conteo/pesaje por contenido al llegar.
* Procurement (``create_procurement_schema``): origen de la OC, vínculo
  recepción↔embarque, peso real y piezas por línea recibida.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.280")

_ARRIVAL_DDL = """CREATE TABLE IF NOT EXISTS logistics_arrival_counts (
        id TEXT NOT NULL PRIMARY KEY, shipment_id TEXT NOT NULL,
        content_id TEXT NOT NULL UNIQUE, received_quantity TEXT NOT NULL,
        received_net_weight TEXT NOT NULL DEFAULT '0', accepted_quantity TEXT NOT NULL,
        rejected_quantity TEXT NOT NULL DEFAULT '0', piece_count INTEGER,
        lot_number TEXT, expiration_date TEXT, temperature TEXT, notes TEXT NOT NULL DEFAULT '',
        counted_by_user_id TEXT NOT NULL, counted_at TEXT NOT NULL, operation_id TEXT NOT NULL)"""


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add(conn, table: str, column: str, ddl: str) -> None:
    columns = _columns(conn, table)
    if columns and column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def run(conn) -> None:
    _add(conn, "supplier_addresses", "label", "TEXT NOT NULL DEFAULT ''")
    for column in ("origin_supplier_address_id", "origin_address_snapshot",
                   "in_transit_at", "receiving_started_at"):
        _add(conn, "logistics_shipments", column, "TEXT")
    conn.execute(_ARRIVAL_DDL)
    create_procurement_schema(conn)
    conn.commit()
    logger.info("280: compra en origen (origen del proveedor, llegada y recepción).")


up = run
