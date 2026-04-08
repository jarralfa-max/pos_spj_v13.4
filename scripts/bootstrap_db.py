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
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Bootstrap DB — pos_spj v13.4")
    parser.add_argument("--db", default="pos_spj.db", help="Ruta al archivo SQLite")
    parser.add_argument("--force", action="store_true", help="Re-ejecutar migraciones ya aplicadas")
    parser.add_argument("--verify-only", action="store_true", help="Solo verificar, no migrar")
    args = parser.parse_args()

    db_path = args.db

    if not args.verify_only:
        logger.info(f"Ejecutando migraciones en: {db_path}")
        try:
            from pos_spj_v13_4.migrations.engine import MigrationEngine  # type: ignore
            engine = MigrationEngine(db_path)
            engine.run_pending()
            logger.info("Migraciones completadas")
        except ImportError:
            # Fallback: importar desde ruta relativa del proyecto
            try:
                import importlib.util
                engine_path = ROOT / "pos_spj_v13.4" / "migrations" / "engine.py"
                spec = importlib.util.spec_from_file_location("engine", engine_path)
                engine_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(engine_mod)
                engine = engine_mod.MigrationEngine(db_path)
                engine.run_pending()
                logger.info("Migraciones completadas (fallback path)")
            except Exception as e:
                logger.error(f"No se pudo cargar el motor de migraciones: {e}")
                logger.warning("Continuando solo con verificación de tablas")

    # Verificar tablas
    from scripts.verify_tables import verificar_tablas
    resultado = verificar_tablas(db_path)

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
