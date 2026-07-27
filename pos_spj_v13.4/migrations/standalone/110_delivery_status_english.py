"""Migrate delivery_orders.estado from Spanish to canonical English enum values.

Spanish → English mapping:
  pendiente    → pending
  preparacion  → preparing
  en_ruta      → in_transit
  entregado    → delivered
  cancelado    → cancelled
  programado   → scheduled
  listo_entrega → ready_for_pickup
  listo_envio  → ready_for_dispatch
  asignado     → assigned
  (legacy aliases included)
"""


def run(conn):
    mapping = (
        ("pendiente_wa",   "pending"),
        ("en_preparacion", "preparing"),
        ("entregada",      "delivered"),
        ("cancelada",      "cancelled"),
        ("en_camino",      "in_transit"),
        ("listo",          "preparing"),
        ("asignado",       "assigned"),
        ("pendiente",      "pending"),
        ("preparacion",    "preparing"),
        ("en_ruta",        "in_transit"),
        ("entregado",      "delivered"),
        ("cancelado",      "cancelled"),
        ("programado",     "scheduled"),
        ("listo_entrega",  "ready_for_pickup"),
        ("listo_envio",    "ready_for_dispatch"),
    )
    for old, new in mapping:
        conn.execute(
            "UPDATE delivery_orders SET estado = ? WHERE estado = ?",
            (new, old),
        )
    conn.commit()
