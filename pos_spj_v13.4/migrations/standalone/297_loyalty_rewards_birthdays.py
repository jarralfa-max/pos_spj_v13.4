"""297 — recompensas de producto con inventario y cumpleaños del cliente (2026-10-03).

Decisiones del usuario:

* La recompensa de tipo PRODUCTO descuenta inventario al confirmarse la entrega
  (sucursal que entrega, a su costo): `loyalty_reward_products` (qué producto
  entrega cada recompensa) y `loyalty_reward_deliveries` (cada salida con su
  costo, que el puente asienta como costo de venta).
* Fecha de nacimiento OPCIONAL y con consentimiento en Clientes:
  `customer_birthdays`. Habilita la regla de bono de cumpleaños y el beneficio
  de cumpleaños de cada programa, que se otorga una vez al año
  (`loyalty_birthday_grants`).

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.297")


def run(conn) -> None:
    from backend.infrastructure.db.schema.customer_birthday_schema import (
        create_customer_birthday_schema,
    )
    from backend.infrastructure.db.schema.loyalty_rules_schema import create_loyalty_rules_schema

    create_loyalty_rules_schema(conn)
    create_customer_birthday_schema(conn)
    conn.commit()
    logger.info("297: recompensas de producto y cumpleaños listos.")


up = run
