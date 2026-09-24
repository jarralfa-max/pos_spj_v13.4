# migrations/standalone/259_price_list_created_by.py
"""259 — price_list.created_by_user_id: hace real la segregación de funciones.

`PricingAuthorizationPolicy.ensure_segregation()` impide que quien crea una
lista de precios sea quien la aprueba o la activa. Estaba implementada y
probada en aislamiento, pero `price_list` sólo guardaba `approved_by_user_id`:
el creador no se persistía en ninguna parte, así que ninguna ruta de producción
podía pasarle el dato y la protección no podía dispararse nunca.

Re-ejecuta el idempotente ``create_pricing_schema`` (mismo patrón que 137/253/
258): el DDL vive sólo en ``pricing_schema.py``, que ahora declara la columna en
el CREATE y la asegura con un ALTER guardado para las tablas creadas por una
ejecución anterior de esa misma función.

Las listas que ya existen quedan con `created_by_user_id` NULL. Es lo correcto:
no se puede inventar quién las creó, y `ensure_segregation` trata un creador
desconocido como "sin restricción" en vez de bloquear una lista histórica.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema

logger = logging.getLogger("spj.migrations.259")


def run(conn) -> None:
    create_pricing_schema(conn)
    conn.commit()
    logger.info("259: price_list.created_by_user_id asegurada.")


up = run
