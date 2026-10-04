"""299 — Integridad de estados de listas de precio y una sola lista base activa.

Tres cosas, todas idempotentes y sin borrar historial:

1. **Estados y tipos heredados → canónicos, SÓLO cuando la conversión es
   inequívoca.** Un estado guardado como ``'active'`` o ``' ACTIVE '`` es
   exactamente ``ACTIVE`` escrito de otra forma; se normaliza. Cualquier otro
   valor (``'activa'``, ``'publicada'``, ``'1'``…) NO se adivina: se deja tal
   cual y se registra en el log. El repositorio ya no revienta con él — informa
   el valor real con `UnknownPriceListStatusError` — y la pantalla lo muestra
   como "estado no reconocido" para que alguien decida.

   Sin esto, una variante de mayúsculas hacía que la lista no apareciera como
   activa en NINGUNA consulta (todas comparan ``status='ACTIVE'`` exacto) y que
   abrirla para operar terminara en "error inesperado".

2. **A lo sumo una lista base activa.** La normalización puede destapar una
   segunda lista base activa (p. ej. ``'active'`` junto a ``'ACTIVE'``). Se
   reaplica la regla que el usuario fijó en la migración 284: queda la que se
   llama ``BASE`` y, si no hay, la de modificación más reciente. Las demás pasan
   a ``INACTIVE`` (no se borran).

3. **El índice único parcial** `ux_price_list_single_active_base`, para que la
   base —y no sólo el caso de uso— impida dos listas base activas.

No toca listas activas VACÍAS: desactivarlas en silencio dejaría a la
instalación sin lista base. La salida es operativa (duplicar, capturar precios,
aprobar y activar la copia, que reemplaza a la vacía) y está descrita en
`migrations/MIGRATION_LOG.md`.
"""

from __future__ import annotations

import importlib
import logging

from backend.domain.pricing.enums import PriceListKind, PriceListStatus
from backend.infrastructure.db.schema.pricing_schema import (
    SINGLE_ACTIVE_BASE_INDEX,
    ensure_single_active_base_index,
)

logger = logging.getLogger("spj.migrations.299")

_STATUSES = tuple(s.value for s in PriceListStatus)
_KINDS = tuple(k.value for k in PriceListKind)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _normalize(conn, column: str, canonical: tuple[str, ...]) -> tuple[int, list]:
    """Normaliza mayúsculas/espacios hacia un valor canónico EXACTO.

    Devuelve (filas normalizadas, [(code, valor) no reconocidos])."""
    normalized = 0
    unknown = []
    for row in conn.execute(f"SELECT id, code, {column} FROM price_list").fetchall():
        raw = row[2]
        if raw in canonical:
            continue
        candidate = str(raw if raw is not None else "").strip().upper()
        if candidate in canonical:
            conn.execute(f"UPDATE price_list SET {column}=?, updated_at=datetime('now') "
                         "WHERE id=?", (candidate, row[0]))
            normalized += 1
            logger.info("299: lista %s: %s %r → %s", row[1], column, raw, candidate)
        else:
            unknown.append((row[1], raw))
    return normalized, unknown


def run(conn) -> None:
    if not _table_exists(conn, "price_list"):
        return
    # Si el índice ya existe (instalación nueva: lo crea la 149), normalizar
    # una variante a 'ACTIVE' podría chocar con él antes de reaplicar la regla
    # de la 284. Un índice no es dato: se suelta y se recrea al final.
    conn.execute(f"DROP INDEX IF EXISTS {SINGLE_ACTIVE_BASE_INDEX}")
    statuses, unknown_statuses = _normalize(conn, "status", _STATUSES)
    kinds, unknown_kinds = _normalize(conn, "kind", _KINDS)
    for code, raw in unknown_statuses:
        logger.warning("299: lista %s con estado no reconocido %r: se deja intacto "
                       "(no se adivina); el módulo de Precios lo señala.", code, raw)
    for code, raw in unknown_kinds:
        logger.warning("299: lista %s con tipo no reconocido %r: se deja intacto.",
                       code, raw)
    conn.commit()

    # Regla de la 284 (decisión del usuario), reaplicada por si la
    # normalización destapó una segunda lista base activa.
    importlib.import_module(
        "migrations.standalone.284_single_active_base_price_list").run(conn)

    if not ensure_single_active_base_index(conn):  # pragma: no cover - defensivo
        logger.warning("299: sigue habiendo más de una lista base activa; "
                       "no se crea el índice único.")
    conn.commit()
    logger.info("299: %s estado(s) y %s tipo(s) normalizados.", statuses, kinds)


up = run
