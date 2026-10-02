"""288 — Folio comercial único de la venta (re-auditoría POS, 2026-10-01).

`sales.sale_number` existía desde el esquema born-clean pero nadie lo
asignaba. Desde esta re-auditoría el cobro reserva ``V-<código>-000001`` del
contador seguro de documentos (`SalesFolioClient`). Esta migración agrega a las
bases existentes el índice único que lo protege, vía `create_sales_schema`
(idempotente: ``CREATE UNIQUE INDEX IF NOT EXISTS``). Las ventas anteriores
quedan con `sale_number` NULL, que el índice parcial admite.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.sales_schema import create_sales_schema

logger = logging.getLogger("spj.migrations.288")


def run(conn) -> None:
    create_sales_schema(conn)
    conn.commit()
    logger.info("288: folio comercial único en ventas.")


up = run
