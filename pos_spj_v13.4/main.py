# main.py — SPJ POS v13
import sys, os, logging, traceback
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

# Must be set before QApplication is constructed when QtWebEngine is loaded
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

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
from interfaz.main_window import MainWindow

_DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "spj_pos_database.db")
# Align connection pool to same DB as bootstrap — prevents "no such table" on fresh start
from core.db.connection import set_db_path as _set_db_path
_set_db_path(DB_PATH)
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

    # Normalización global de botones en TODOS los diálogos (evita full-width).
    try:
        from modulos.ui_components import install_dialog_button_normalizer
        install_dialog_button_normalizer(app)
        logger.info("✅ Normalizador global de diálogos activo")
    except Exception as _dn:
        logger.warning("Normalizador de diálogos no aplicado: %s", _dn)

    if not _instancia_unica(app):
        QMessageBox.information(None, "Ya está ejecutándose",
            "SPJ POS ya está abierto en esta computadora.")
        sys.exit(0)

    # ── Bootstrap de base de datos: secuencia única (SHELL-4) ────────────────
    # Integridad → migraciones → validación de esquema/UUIDv7 → estado de
    # instalación, en UNA sola pasada (backend.bootstrap.run_database_bootstrap).
    # Reemplaza las tres rutas que existían antes (_bootstrap_db con su propio
    # fallback interno, una llamada duplicada a bootstrap_database(), y un
    # tercer bloque con su propia conexión y manejo de errores) — ninguna de
    # ellas coincidía exactamente en qué migraba ni en qué consideraba fatal.
    # Un fallo aquí SIEMPRE detiene el arranque: la ruta vieja tenía un
    # `except Exception` que registraba el fallo como advertencia y dejaba
    # continuar la app sobre un esquema posiblemente a medio migrar — eso ya
    # no puede pasar (ver docs/refactor/application_bootstrap_audit.md).
    from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence

    result = run_database_bootstrap_sequence(DB_PATH)
    if not result.success:
        failed = result.failed_step()
        if failed is not None and failed.step_name == "database_integrity":
            logger.critical("BD dañada: %s", failed.message)
            resp = QMessageBox.critical(
                None, "Base de datos dañada",
                f"La base de datos presenta problemas de integridad "
                f"({failed.message}).\n\n¿Restaurar el último backup?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
            if resp == QMessageBox.Yes and _restaurar_backup(DB_PATH):
                result = run_database_bootstrap_sequence(DB_PATH)

    if not result.success:
        failed = result.failed_step()
        detail = failed.message if failed else "Fallo desconocido durante el arranque de la base de datos."
        logger.critical("Bootstrap de base de datos falló (%s): %s",
                         failed.step_name if failed else "?", detail)
        if result.context.conn is not None:
            try: result.context.conn.close()
            except Exception: pass
        QMessageBox.critical(None, "Error Fatal — Base de datos", detail)
        sys.exit(1)

    for warning_msg in result.warnings:
        logger.warning(warning_msg)
    from backend.bootstrap.installation_setup import ensure_installation_provisioned

    try:
        if not ensure_installation_provisioned(result.context.conn):
            logger.info("Configuración inicial cancelada o instalación bloqueada.")
            sys.exit(0)
    except Exception as exc:
        logger.exception("No se pudo verificar la configuración inicial.")
        QMessageBox.critical(None, "Error de configuración inicial", str(exc))
        sys.exit(1)
    finally:
        if result.context.conn is not None:
            result.context.conn.close()
    logger.info("✅ Bootstrap de base de datos OK (%s)", result.final_state.value)

    try:
        container = AppContainer(db_path=DB_PATH)
        logger.info("✅ AppContainer activo")
    except Exception as e:
        logger.critical("AppContainer falló: %s", e)
        QMessageBox.critical(None, "Error Fatal",
            f"No se pudo inicializar el sistema:\n\n{e}")
        sys.exit(1)

    # Intenta arrancar el microservicio WhatsApp en segundo plano
    try:
        from core.services.microservice_launcher import launch_microservice_async
        from pathlib import Path
        app_root = Path(__file__).parent.parent
        launch_microservice_async(app_root)
        logger.info("Verificando microservicio WhatsApp...")
    except Exception as e:
        logger.debug("Launcher de microservicio no disponible: %s", e)

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
