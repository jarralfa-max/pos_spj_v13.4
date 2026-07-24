# migrations/standalone/153_products_yields_backfill_from_legacy.py
"""PROD-19 paso 5 — backfill de rendimientos legacy → yield_profile canónico.

Copia (idempotente, aditiva) el rendimiento solo-pollo legacy al esquema canónico
versionado multi-especie (`yield_profiles` → `yield_profile_versions` v1 →
`yield_outputs`):

    rendimiento_pollo       (producto de entrada: pollo entero)   → yield_profiles
    rendimiento_derivados   (cortes/derivados con % rendimiento)  → yield_outputs

Reglas:
- **Idempotente**: ids legacy preservados como PK (INSERT OR IGNORE); v1 de-duplicada
  por UNIQUE(yield_profile_id, version_number).
- **Decimal-only**: porcentajes REAL → string Decimal.
- **Aditivo**: legacy intacto; en DB fresca (0 filas) es no-op.
- `es_subproducto=1` → output_type BY_PRODUCT, si no MAIN. Unidad = KG.

NO cubiertos aquí (analítica de corridas, otro contexto): `meat_production_yields`,
`production_yield_analysis`.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.153")


def run(conn) -> None:
    n = _backfill_pollo_yields(conn)
    conn.commit()
    logger.info("153: backfill rendimientos → yield_profiles (%d perfiles).", n)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _cols(conn, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _dec(value, default="0") -> str:
    if value in (None, ""):
        return default
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.0001")))
    except (InvalidOperation, ValueError):
        return default


def _backfill_pollo_yields(conn) -> int:
    if not _table_exists(conn, "rendimiento_pollo"):
        return 0
    if "producto_pollo_id" not in _cols(conn, "rendimiento_pollo"):
        return 0
    rows = conn.execute(
        "SELECT id, producto_pollo_id FROM rendimiento_pollo").fetchall()
    n = 0
    for pid, pollo_id in rows:
        if not pid or not pollo_id:
            continue
        created = conn.execute(
            "INSERT OR IGNORE INTO yield_profiles (id, input_product_id, species_id, "
            "name, active) VALUES (?,?,NULL,?,1)",
            (pid, pollo_id, f"Rendimiento {str(pollo_id)[:8]}")).rowcount or 0
        n += created
        vid = _ensure_version(conn, pid)
        _migrate_outputs(conn, version_id=vid, pollo_id=pollo_id)
    return n


def _ensure_version(conn, profile_id: str) -> str:
    row = conn.execute(
        "SELECT id FROM yield_profile_versions WHERE yield_profile_id=? "
        "AND version_number=1", (profile_id,)).fetchone()
    if row:
        return row[0]
    vid = new_uuid()
    conn.execute(
        "INSERT OR IGNORE INTO yield_profile_versions (id, yield_profile_id, "
        "version_number, status, tolerance_pct) VALUES (?,?,1,'ACTIVE','0')",
        (vid, profile_id))
    return conn.execute(
        "SELECT id FROM yield_profile_versions WHERE yield_profile_id=? "
        "AND version_number=1", (profile_id,)).fetchone()[0]


def _migrate_outputs(conn, *, version_id: str, pollo_id: str) -> None:
    if not _table_exists(conn, "rendimiento_derivados"):
        return
    cols = _cols(conn, "rendimiento_derivados")
    if "producto_derivado_id" not in cols or "producto_pollo_id" not in cols:
        return
    sub = "es_subproducto" if "es_subproducto" in cols else "0 AS es_subproducto"
    rows = conn.execute(
        f"SELECT id, producto_derivado_id, porcentaje_rendimiento, {sub} "
        "FROM rendimiento_derivados WHERE producto_pollo_id=?", (pollo_id,)).fetchall()
    for seq, (did, deriv_id, pct, es_sub) in enumerate(rows):
        if not deriv_id:
            continue
        out_id = did or new_uuid()
        output_type = "BY_PRODUCT" if int(es_sub or 0) else "MAIN"
        conn.execute(
            "INSERT OR IGNORE INTO yield_outputs (id, version_id, product_id, "
            "output_type, expected_yield_pct, expected_quantity, unit_id, "
            "cost_allocation_weight, sequence) VALUES (?,?,?,?,?,?,?,?,?)",
            (out_id, version_id, deriv_id, output_type, _dec(pct), "0", "KG", "0", seq))


up = run
