"""Punto de entrada de la aplicación de escritorio.

`main.py` sólo llama a `main()`; toda la secuencia de arranque vive aquí (§0).
El orden importa y cada paso depende del anterior:

    1. QApplication          — antes de cualquier widget o diálogo.
    2. Instancia única        — antes de tocar la base de datos.
    3. Base de datos          — integridad -> migraciones -> validación de
                                esquema/UUID -> estado de instalación, en UNA
                                sola pasada (`run_database_bootstrap_sequence`).
    4. Grafo de dependencias  — `CompositionRoot` valida y construye.
    5. Autenticación          — asistente de primer arranque si hace falta,
                                luego login. Devuelve un `ApplicationContext`.
    6. Ventana                — se construye SÓLO tras autenticar, con el
                                contexto ya resuelto.

DÓNDE ESTÁ LA BASE DE DATOS — no se toca
----------------------------------------
Se usa `<raíz>/data/spj_pos_database.db`, exactamente la misma ruta de siempre.
Es tentador cambiarla por `AppPaths.sqlite_database_path()`, que es la
resolución canónica de rutas del proyecto, pero apunta a otro sitio Y con otro
nombre de archivo (`%APPDATA%/SPJ/SPJ ERP POS/db/spj.sqlite3`). Hacer ese
cambio aquí no daría ningún error: la aplicación arrancaría contra una base
vacía, la migraría entera y mostraría el asistente de primer arranque, como si
la instalación fuera nueva. Los datos reales seguirían en disco, invisibles.
Reconciliar ambas rutas es una migración deliberada, con copia y verificación —
no un efecto secundario de mover el arranque de sitio.

UN FALLO DE ARRANQUE DETIENE EL ARRANQUE
----------------------------------------
Cualquier paso FATAL corta aquí. La ruta anterior capturaba las excepciones del
motor de migraciones, las registraba como advertencia y dejaba continuar sobre
un esquema a medio migrar; eso es justo lo que §9 prohíbe y no puede volver a
pasar por este camino.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.shared.app_version import APP_NAME, VERSION

logger = logging.getLogger("SPJ.Boot")

#: Raíz del proyecto — `frontend/desktop/app.py` está tres niveles por debajo.
#: El mismo error que ya se documentó en `backend/infrastructure/db/connection.py`:
#: contar mal los niveles no rompe nada visiblemente, sólo crea la base de datos
#: en otra carpeta.
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(APP_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "spj_pos_database.db")
LOGS_DIR = os.path.join(APP_ROOT, "logs")

#: Se mantiene vivo mientras corre la aplicación: si el `QLocalServer` se
#: recolecta, el nombre queda libre y una segunda instancia podría abrirse.
_LOCAL_SERVER = None


def _install_crash_handler() -> None:
    def _handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "ERROR NO CAPTURADO:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        try:
            if QApplication.instance():
                QMessageBox.critical(
                    None, f"Error inesperado — {APP_NAME}",
                    f"Ocurrió un error no esperado.\n\n{exc_type.__name__}: {exc_value}\n\n"
                    f"Revisa logs/spj_pos.log para más detalles.",
                )
        except Exception:
            # Un fallo AL INFORMAR de un fallo no debe sustituir al original:
            # se deja pasar y se delega en el manejador por defecto, que sí lo
            # imprimirá.
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler


def _is_only_instance() -> bool:
    """False si ya hay otra instancia abierta sobre la MISMA base de datos.

    El nombre del servidor local incluye la ruta de la base: dos instalaciones
    con bases distintas sí pueden convivir, dos sobre la misma no.
    """
    global _LOCAL_SERVER
    try:
        from PyQt5.QtNetwork import QLocalServer, QLocalSocket

        name = f"SPJ_POS_{os.path.abspath(DB_PATH).replace(os.sep, '_')}"
        probe = QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(300):
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(name)
        _LOCAL_SERVER = QLocalServer()
        _LOCAL_SERVER.listen(name)
    except Exception as exc:
        # Sin comprobación de instancia única se puede seguir trabajando; sin
        # aplicación, no. Se avisa y se continúa.
        logger.warning("No se pudo verificar la instancia única: %s", exc)
    return True


def _prepare_database() -> object:
    """Deja la base lista y devuelve la conexión viva, o termina el proceso.

    La conexión que devuelve la secuencia de arranque es la que se usa después
    para autenticar y componer la ventana: abrir una segunda conexión al mismo
    archivo sería un segundo escritor WAL sin ninguna ventaja.
    """
    from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
    from backend.infrastructure.db.connection import set_db_path

    os.makedirs(DATA_DIR, exist_ok=True)
    # El pool de conexiones tiene que apuntar al mismo archivo que se acaba de
    # migrar; si no, los repositorios leerían de otra base y el síntoma sería
    # "no such table" con la migración recién aplicada.
    set_db_path(DB_PATH)

    result = run_database_bootstrap_sequence(DB_PATH)
    if not result.success:
        failed = result.failed_step()
        detalle = failed.message if failed else "Fallo desconocido al preparar la base de datos."
        logger.critical(
            "El arranque de la base de datos falló (%s): %s",
            failed.step_name if failed else "?", detalle)
        if result.context.conn is not None:
            try:
                result.context.conn.close()
            except Exception:
                pass
        QMessageBox.critical(None, "Error fatal — Base de datos", detalle)
        sys.exit(1)

    for advertencia in result.warnings:
        logger.warning(advertencia)
    logger.info("Base de datos lista (%s).", result.final_state.value)
    return result


def _build_services():
    from backend.bootstrap.composition_root import CompositionRoot
    from backend.bootstrap.wiring.database_wiring import DatabaseModuleProvider
    from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider
    from backend.bootstrap.wiring.shared_wiring import SharedModuleProvider

    return CompositionRoot([
        SharedModuleProvider(), SecurityModuleProvider(), DatabaseModuleProvider(),
    ]).build()


def main() -> int:
    """Arranca la aplicación. Devuelve el código de salida del proceso."""
    from pathlib import Path

    from frontend.desktop.logging_setup import configure_logging

    configure_logging(Path(LOGS_DIR))
    _install_crash_handler()
    logger.info("=" * 55)
    logger.info("  %s v%s", APP_NAME, VERSION)
    logger.info("=" * 55)

    # Debe fijarse ANTES de construir la QApplication cuando se carga QtWebEngine.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    try:
        from frontend.desktop.themes.theme_manager import ThemeManager

        ThemeManager.instance().apply(app)
    except Exception as exc:
        logger.warning("No se pudo aplicar el tema guardado: %s", exc)

    if not _is_only_instance():
        QMessageBox.information(
            None, "Ya está ejecutándose",
            f"{APP_NAME} ya está abierto en esta computadora.")
        return 0

    bootstrap = _prepare_database()
    connection = bootstrap.context.conn
    services = _build_services()

    ventana = {}

    def _on_authenticated(context) -> None:
        """Se llama una sola vez, con el login ya resuelto."""
        from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
        from frontend.desktop.shell.desktop_shell_window_composition import (
            build_application_window,
        )

        window = build_application_window(
            context=context,
            connection=connection,
            session_context=LegacySessionAdapter(context),
            health_report=bootstrap.health_report,
        )
        window.setWindowTitle(f"{APP_NAME} v{VERSION}")
        window.show()
        ventana["window"] = window
        logger.info("Sesión iniciada: %s en %s.", context.user_name, context.branch_name)

    from frontend.desktop.shell.desktop_shell_authentication_composition import (
        build_authentication_coordinator,
    )

    coordinator = build_authentication_coordinator(
        connection=connection, container=services, on_authenticated=_on_authenticated,
    )

    # `run()` cubre el asistente de primer arranque, la instalación bloqueada,
    # la que requiere recuperación y el login. False significa "no hay nada más
    # que hacer": se sale sin ventana y sin error.
    if not coordinator.run():
        logger.info("Arranque cancelado antes de abrir la aplicación.")
        return 0

    exit_code = app.exec_()
    logger.info("Sistema cerrado. Código: %s", exit_code)
    return exit_code
