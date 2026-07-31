# migrations/standalone/170_pos_barcodes_images_backfill_from_legacy.py
"""P0-B slice 6 (enabler) — backfill de códigos de barras e imágenes legacy → canónico.

El catálogo POS se repunta a `products` + satélites canónicos. Dos campos que el
POS consume no tenían backfill legacy→canónico y su repunte sin este seed
regresaría (escaneo de código de barras e imágenes en blanco):

- `productos.codigo_barras` → `product_barcodes` (primario, tipo LEGACY);
- `productos.imagen_path`  → `product_images` (primaria).

Sólo para productos que ya existen en el maestro canónico `products` (ids
preservados). Idempotente: no duplica (guarda por existencia). UUIDv7 vía
`new_uuid()`. No modifica `productos` ni `products`.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.170")


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _col(conn, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def run(conn) -> None:
    if not _table(conn, "productos") or not _table(conn, "products"):
        logger.info("170: falta productos o products; backfill omitido.")
        return

    bc = img = 0
    # ── códigos de barras ────────────────────────────────────────────────────
    if _table(conn, "product_barcodes") and _col(conn, "productos", "codigo_barras"):
        rows = conn.execute(
            "SELECT pr.id, pr.codigo_barras FROM productos pr "
            "JOIN products p ON p.id = pr.id "
            "WHERE COALESCE(pr.codigo_barras,'') != ''").fetchall()
        for product_id, barcode in rows:
            exists = conn.execute(
                "SELECT 1 FROM product_barcodes WHERE product_id=? AND barcode_value=? LIMIT 1",
                (product_id, str(barcode))).fetchone()
            if exists:
                continue
            has_primary = conn.execute(
                "SELECT 1 FROM product_barcodes WHERE product_id=? AND is_primary=1 LIMIT 1",
                (product_id,)).fetchone()
            conn.execute(
                "INSERT INTO product_barcodes (id, product_id, barcode_value, "
                "barcode_type, is_primary, active) VALUES (?,?,?,?,?,1)",
                (new_uuid(), product_id, str(barcode), "LEGACY",
                 0 if has_primary else 1))
            bc += 1

    # ── imágenes ──────────────────────────────────────────────────────────────
    if _table(conn, "product_images") and _col(conn, "productos", "imagen_path"):
        rows = conn.execute(
            "SELECT pr.id, pr.imagen_path FROM productos pr "
            "JOIN products p ON p.id = pr.id "
            "WHERE COALESCE(pr.imagen_path,'') != ''").fetchall()
        for product_id, uri in rows:
            has_img = conn.execute(
                "SELECT 1 FROM product_images WHERE product_id=? LIMIT 1",
                (product_id,)).fetchone()
            if has_img:
                continue
            conn.execute(
                "INSERT INTO product_images (id, product_id, uri, is_primary, sort_order) "
                "VALUES (?,?,?,1,0)", (new_uuid(), product_id, str(uri)))
            img += 1

    conn.commit()
    logger.info("170: backfill POS legacy→canónico (%d barcodes, %d imágenes).", bc, img)


up = run
