
# migrations/standalone/037_product_images.py
# ── Imágenes de Producto ───────────────────────────────────────────────────────
# Asegura columna imagen_path en tabla productos.
# Crea directorio imagenes_productos si no existe.
import logging, sqlite3, os
logger = logging.getLogger("spj.migrations.037")

def run(conn: sqlite3.Connection) -> None:
    _patch_productos(conn)
    _ensure_images_dir()
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 037: imagen_path en productos completada.")

def _add_col_safe(conn, tabla, col, defn):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    if col not in existing:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {defn}")
        logger.debug("Columna %s.%s añadida.", tabla, col)

def _patch_productos(conn):
    _add_col_safe(conn, "productos", "imagen_path", "TEXT")
    logger.info("Columna imagen_path verificada en productos.")

def _ensure_images_dir():
    os.makedirs("imagenes_productos", exist_ok=True)
    logger.info("Directorio imagenes_productos verificado.")
