"""284 — Exactamente UNA lista de precios base activa.

Medido el 2026-09-30 en la base viva: dos listas `kind='BASE'` activas a la vez
(`BASE · Lista base`, sembrada por la instalación, y `ORIGIN-00001`, creada y
aprobada el 25/09). `active_list_of_kind` toma la de modificación más reciente,
así que mandaba ORIGIN-00001 sin que nadie lo hubiera decidido. Ninguna tenía
precios capturados.

Decisión del usuario (2026-09-30): queda activa la que se llama `BASE`; las demás
se desactivan. Si no hay ninguna con ese código, se conserva la de modificación
más reciente (la que ya mandaba) para no cambiar el precio vigente. Desde ahora
`ActivatePriceListUseCase` reemplaza a la anterior al activar otra lista base.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.migrations.284")


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='price_list'"
                    ).fetchone() is None:
        return
    active = conn.execute(
        "SELECT id, code FROM price_list WHERE kind='BASE' AND status='ACTIVE'"
        " ORDER BY COALESCE(updated_at, created_at) DESC").fetchall()
    if len(active) <= 1:
        return
    keep = next((row[0] for row in active if str(row[1]).upper() == "BASE"), active[0][0])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in active:
        if row[0] != keep:
            conn.execute("UPDATE price_list SET status='INACTIVE', updated_at=? WHERE id=?",
                         (now, row[0]))
            logger.info("284: lista base %s desactivada (queda una sola activa).", row[1])
    conn.commit()


up = run
