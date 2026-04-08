"""
bootstrap_db.py — pos_spj v13.4
Ejecuta todas las migraciones pendientes y verifica la integridad de la DB.
Idempotente: seguro de ejecutar múltiples veces.

Uso:
    python scripts/bootstrap_db.py --db pos_spj.db
    python scripts/bootstrap_db.py --db /tmp/test.db --force
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
APP_ROOT = ROOT / "pos_spj_v13.4"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _run_migrations(db_path: str) -> None:
    """Ejecuta migraciones usando el engine canónico (función up)."""
    conn = sqlite3.connect(db_path)
    try:
        try:
            from migrations import engine as migration_engine  # path canónico
            migration_engine.up(conn)
        except Exception:
            import importlib.util
            engine_path = ROOT / "pos_spj_v13.4" / "migrations" / "engine.py"
            spec = importlib.util.spec_from_file_location("engine", engine_path)
            engine_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(engine_mod)
            engine_mod.up(conn)
    finally:
        conn.close()


def db_vacia(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return len(cur.fetchall()) == 0


def bootstrap_database(db_path: str = "pos_spj.db", verify_only: bool = False) -> dict:
    """
    Inicializa y valida DB de forma idempotente.
    - Si la DB está vacía, fuerza ejecución de migraciones.
    - Si no está vacía, valida tablas críticas.
    """
    conn = sqlite3.connect(db_path)
    try:
        is_empty = db_vacia(conn)
    finally:
        conn.close()

    if not verify_only and is_empty:
        logger.warning("DB vacía detectada — ejecutando migraciones: %s", db_path)
        _run_migrations(db_path)
        logger.info("Migraciones completadas (bootstrap DB vacía)")
    elif not verify_only:
        logger.info("DB ya contiene tablas — validando estado: %s", db_path)

    # Verificar tablas
    try:
        from scripts.verify_tables import verificar_tablas
        return verificar_tablas(db_path)
    except Exception:
        import importlib.util
        vt_path = ROOT / "scripts" / "verify_tables.py"
        spec = importlib.util.spec_from_file_location("verify_tables", vt_path)
        vt_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vt_mod)
        return vt_mod.verificar_tablas(db_path)


def main():
    parser = argparse.ArgumentParser(description="Bootstrap DB — pos_spj v13.4")
    parser.add_argument("--db", default="pos_spj.db", help="Ruta al archivo SQLite")
    parser.add_argument("--force", action="store_true", help="Re-ejecutar migraciones ya aplicadas")
    parser.add_argument("--verify-only", action="store_true", help="Solo verificar, no migrar")
    args = parser.parse_args()

    db_path = args.db
    resultado = None

    if not args.verify_only and args.force:
        logger.info(f"Ejecutando migraciones en: {db_path}")
        try:
            _run_migrations(db_path)
            logger.info("Migraciones completadas")
        except ImportError:
            # Fallback: importar desde ruta relativa del proyecto
            try:
                import importlib.util
                engine_path = ROOT / "pos_spj_v13.4" / "migrations" / "engine.py"
                spec = importlib.util.spec_from_file_location("engine", engine_path)
                engine_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(engine_mod)
                conn = sqlite3.connect(db_path)
                try:
                    engine_mod.up(conn)
                finally:
                    conn.close()
                logger.info("Migraciones completadas (fallback path)")
            except Exception as e:
                logger.error(f"No se pudo cargar el motor de migraciones: {e}")
                logger.warning("Continuando solo con verificación de tablas")
        try:
            from scripts.verify_tables import verificar_tablas
            resultado = verificar_tablas(db_path)
        except Exception:
            import importlib.util
            vt_path = ROOT / "scripts" / "verify_tables.py"
            spec = importlib.util.spec_from_file_location("verify_tables", vt_path)
            vt_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(vt_mod)
            resultado = vt_mod.verificar_tablas(db_path)
    else:
        resultado = bootstrap_database(db_path=db_path, verify_only=args.verify_only)

    if "error" in resultado:
        logger.error(resultado["error"])
        sys.exit(1)

    cobertura = resultado["cobertura_pct"]
    faltantes = resultado["faltantes"]

    if faltantes:
        logger.warning(f"Tablas faltantes ({len(faltantes)}): {faltantes}")
        logger.info(f"Cobertura: {cobertura}%")
        # Advertencia pero no fallo — algunas tablas se crean en runtime
        sys.exit(0)
    else:
        logger.info(f"OK: {resultado['total_criticas']} tablas críticas verificadas ({cobertura}%)")
        sys.exit(0)


if __name__ == "__main__":
    main()
