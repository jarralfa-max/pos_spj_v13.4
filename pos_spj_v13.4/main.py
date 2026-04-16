# main.py — SPJ POS v13
import sys, os, logging, traceback
from PyQt5.QtWidgets import QApplication, QMessageBox

# Asegurar que el directorio del proyecto esté PRIMERO en el path
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

# ── Logging ───────────────────────────────────────────────────────────────────
try:
    from core.logging_setup import setup_logging
    setup_logging()
except Exception:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler("spj_pos.log", encoding="utf-8")])

from version import __version__, __app_name__
logger = logging.getLogger("SPJ.Boot")

# ── Crash handler global ──────────────────────────────────────────────────────
def _crash_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb); return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("ERROR NO CAPTURADO:\n%s", msg)
    try:
        if QApplication.instance():
            QMessageBox.critical(None, "Error inesperado — SPJ POS",
                f"Ocurrió un error no esperado.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Revisa spj_pos.log para más detalles.")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _crash_handler

# ── Imports principales ───────────────────────────────────────────────────────
from core.app_container import AppContainer
from migrations import engine as migrator
from interfaz.main_window import MainWindow
from scripts.bootstrap_db import bootstrap_database


def _bootstrap_db(db_path: str) -> None:
    """
    Ejecuta bootstrap DB con fallback seguro para layouts donde /scripts no existe.
    """
    try:
        from scripts.bootstrap_db import bootstrap_database
        bootstrap_database(db_path)
        return
    except Exception as e:
        logger.warning("bootstrap_db externo no disponible (%s). Usando fallback interno.", e)

    # Fallback interno: migrar + validar sin depender del módulo scripts
    import sqlite3
    from core.db.connection import migrate_db, verificar_tablas

    conn = sqlite3.connect(db_path)
    try:
        migrator.up(conn)
        migrate_db(conn)
        verificar_tablas(conn)
    finally:
        conn.close()

DB_PATH = "spj_pos_database.db"
# Align connection pool to same DB as bootstrap — prevents "no such table" on fresh start
from core.db.connection import set_db_path as _set_db_path
_set_db_path(os.path.abspath(DB_PATH))
_LOCAL_SERVER = None

def _instancia_unica(app) -> bool:
    global _LOCAL_SERVER
    try:
        from PyQt5.QtNetwork import QLocalServer, QLocalSocket
        name = f"SPJ_POS_{os.path.abspath(DB_PATH).replace(os.sep,'_')}"
        sock = QLocalSocket()
        sock.connectToServer(name)
        if sock.waitForConnected(300):
            sock.disconnectFromServer(); return False
        QLocalServer.removeServer(name)
        _LOCAL_SERVER = QLocalServer()
        _LOCAL_SERVER.listen(name)
    except Exception as e:
        logger.warning("instancia_unica: %s", e)
    return True

def _verificar_bd(path: str) -> bool:
    import sqlite3
    if not os.path.exists(path): return True
    try:
        conn = sqlite3.connect(path)
        r = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if r and r[0] == "ok":
            logger.info("✅ Integridad BD OK"); return True
        raise sqlite3.DatabaseError(r[0] if r else "unknown")
    except Exception as e:
        logger.critical("BD dañada: %s", e)
        resp = QMessageBox.critical(None, "⚠️ Base de datos dañada",
            f"La BD presenta problemas de integridad ({e}).\n\n"
            "¿Restaurar el último backup?",
            QMessageBox.Yes | QMessageBox.Ignore | QMessageBox.Cancel,
            QMessageBox.Yes)
        if resp == QMessageBox.Cancel: return False
        if resp == QMessageBox.Yes:
            return _restaurar_backup(path)
        return True

def _restaurar_backup(path: str) -> bool:
    import shutil
    try:
        from modulos.sistema.backup_engine import listar_backups
        backups = listar_backups()
        if not backups:
            QMessageBox.warning(None, "Sin backups", "No hay backups disponibles."); return False
        bpath = backups[-1] if isinstance(backups[-1], str) else backups[-1].get("path","")
        if not bpath or not os.path.exists(bpath):
            return False
        shutil.move(path, path + ".damaged")
        shutil.copy2(bpath, path)
        QMessageBox.information(None, "✅ Backup restaurado",
            f"Backup restaurado: {os.path.basename(bpath)}")
        return True
    except Exception as e:
        QMessageBox.critical(None, "Error", str(e)); return False

def inicializar_sistema():
    logger.info("═"*55)
    logger.info("  %s v%s", __app_name__, __version__)
    logger.info("═"*55)

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)

    # ── Aplicar tema guardado ANTES de mostrar cualquier ventana ─────────────
    try:
        from ui.themes.theme_engine import load_saved_theme
        load_saved_theme(None)   # None → aplica solo a QApplication
        logger.info("✅ Tema aplicado al arranque")
    except Exception as _te:
        logger.warning("Tema no aplicado al arranque: %s", _te)

    if not _instancia_unica(app):
        QMessageBox.information(None, "Ya está ejecutándose",
            "SPJ POS ya está abierto en esta computadora.")
        sys.exit(0)

    if not _verificar_bd(DB_PATH):
        sys.exit(1)

    try:
        _bootstrap_db(DB_PATH)
        bootstrap_database(DB_PATH)
        logger.info("✅ Bootstrap DB OK")
    except Exception as e:
        logger.critical("Bootstrap DB falló: %s", e)
        QMessageBox.critical(None, "Error Fatal — Bootstrap DB", str(e))
        sys.exit(1)

    try:
        import sqlite3
        from core.db.connection import migrate_db, verificar_tablas
        conn = sqlite3.connect(DB_PATH)
        migrator.up(conn)
        migrate_db(conn)
        verificar_tablas(conn)
        conn.close()
        logger.info("✅ Migraciones OK")
    except RuntimeError as e:
        try:
            conn.close()
        except Exception:
            pass
        logger.critical("DB incompleta post-migraciones: %s", e)
        QMessageBox.critical(None, "Error Fatal — DB incompleta", str(e))
        sys.exit(1)
    except Exception as e:
        logger.warning("Migraciones (continuando): %s", e)

    try:
        container = AppContainer(db_path=DB_PATH)
        logger.info("✅ AppContainer activo")
    except Exception as e:
        logger.critical("AppContainer falló: %s", e)
        QMessageBox.critical(None, "Error Fatal",
            f"No se pudo inicializar el sistema:\n\n{e}")
        sys.exit(1)

    try:
        if hasattr(container, "whatsapp_webhook"):
            container.whatsapp_webhook.start()
    except Exception as e:
        logger.warning("WA webhook: %s", e)

    try:
        window = MainWindow(container)
        window.show()
        logger.info("✅ UI lista")
    except Exception as e:
        logger.critical("UI falló: %s", e)
        QMessageBox.critical(None, "Error Fatal", str(e))
        sys.exit(1)

    try:
        from core.services.version_checker import VersionChecker
        # v13.2 fix: store as window attribute so GC doesn't destroy it
        # while the QThread is still running (was causing "QThread: Destroyed" warning)
        window._version_checker = VersionChecker(__version__, parent=window)
        window._version_checker.check_async(
            lambda info: window.mostrar_notif_update(info) if info else None)
    except Exception:
        pass

    exit_code = app.exec_()

    for cleanup in [
        lambda: container.whatsapp_webhook.stop() if hasattr(container,"whatsapp_webhook") else None,
        lambda: container.close(),
        lambda: _LOCAL_SERVER.close() if _LOCAL_SERVER else None,
    ]:
        try: cleanup()
        except Exception: pass

    logger.info("Sistema cerrado. Código: %s", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    inicializar_sistema()
