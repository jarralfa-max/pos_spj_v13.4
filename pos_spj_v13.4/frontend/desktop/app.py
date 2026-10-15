"""Punto de entrada de la aplicación de escritorio.

`main.py` sólo llama a `main()`; toda la secuencia de arranque vive aquí (§0).
El orden importa y cada paso depende del anterior:

    0. `--self-test`          — arranque sin ventana para el actualizador y la
                                CI (`backend/bootstrap/self_test.py`).
    1. QApplication          — antes de cualquier widget o diálogo.
    2. Actualización          — ¿hay un actualizador corriendo, o una
                                actualización que requiere recuperación?
                                (`UpdateStartupGate`). Antes de abrir la base.
    3. Instancia única        — candado sobre la base (`InstanceLock`), visible
                                también para el actualizador externo.
    4. Reubicación            — una base anterior al instalador se traslada UNA
                                vez, con respaldo y verificación.
    5. Base de datos          — integridad -> compatibilidad de esquema ->
                                migraciones -> validación de esquema/UUID ->
                                estado de instalación, en UNA sola pasada.
    6. Inventario de versión  — versión/esquema de la estación y resultado de
                                la última actualización.
    7. Grafo de dependencias  — `CompositionRoot` valida y construye.
    8. Autenticación          — asistente de primer arranque si hace falta,
                                luego login. Devuelve un `ApplicationContext`.
    9. Ventana                — se construye SÓLO tras autenticar.

DÓNDE ESTÁ LA BASE DE DATOS
---------------------------
La resuelve `AppPaths.database_path` — la MISMA resolución que usan el pool de
conexiones, el actualizador, los respaldos y el servicio WhatsApp local:

* desde el código fuente: `<raíz>/data/spj_pos_database.db`, la ruta de
  siempre (los manuales de reinicio de la base de desarrollo la usan);
* instalado: `<carpeta de datos>/db/spj_pos_database.db`, en ProgramData o en
  LocalAppData según el instalador.

Cambiar la ruta nunca arranca sobre una base vacía: si existe una base anterior
conocida, `LegacyDatabaseRelocator` la traslada con respaldo y verificación, y
ante cualquier duda (dos bases, base reubicada que desapareció) el arranque se
detiene con el diagnóstico.

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

from backend.shared.app_paths import DATABASE_FILENAME, AppPaths
from backend.shared.app_version import APP_NAME, VERSION
from backend.shared.install_config import InstallConfigError

logger = logging.getLogger("SPJ.Boot")

#: Raíz del código del paquete — `frontend/desktop/app.py` está tres niveles
#: por debajo. Sólo describe dónde está el código; las rutas de datos salen de
#: `AppPaths`.
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    PATHS: AppPaths | None = AppPaths.from_environment()
    _PATHS_ERROR: Exception | None = None
except InstallConfigError as _exc:  # se informa en main(), con ventana
    PATHS = None
    _PATHS_ERROR = _exc

#: Sin `install_config.json` legible no se abre ninguna base (main() se detiene
#: antes); el valor sólo existe para que el módulo se pueda importar.
DB_PATH = str(PATHS.database_path) if PATHS else os.path.join(APP_ROOT, "data", DATABASE_FILENAME)
DATA_DIR = os.path.dirname(DB_PATH)
LOGS_DIR = str(PATHS.logs_dir) if PATHS else os.path.join(APP_ROOT, "logs")

#: Candado de instancia única; se mantiene vivo mientras corre la aplicación.
_INSTANCE_LOCK = None


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
                    f"Revisa {os.path.join(LOGS_DIR, 'spj_pos.log')} para más detalles.",
                )
        except Exception:
            # Un fallo AL INFORMAR de un fallo no debe sustituir al original:
            # se deja pasar y se delega en el manejador por defecto, que sí lo
            # imprimirá.
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _handler


def _acquire_instance_lock() -> bool:
    """False si ya hay otra instancia (o el actualizador) sobre la MISMA base.

    Un candado de archivo junto a la base: dos instalaciones con bases
    distintas sí pueden convivir, dos sobre la misma no. A diferencia del
    `QLocalServer` anterior, lo ve también el actualizador externo, que no es
    un proceso Qt. El sistema operativo lo libera si el proceso muere.
    """
    global _INSTANCE_LOCK
    from backend.infrastructure.runtime.instance_lock import InstanceLock

    lock = InstanceLock(_instance_lock_path())
    try:
        if not lock.acquire(timeout_seconds=2.0):
            return False
    except OSError as exc:
        # Sin comprobación de instancia única se puede seguir trabajando; sin
        # aplicación, no. Se avisa y se continúa.
        logger.warning("No se pudo verificar la instancia única: %s", exc)
        return True
    _INSTANCE_LOCK = lock
    return True


def _instance_lock_path() -> str:
    return DB_PATH + ".lock"


def _release_instance_lock() -> None:
    global _INSTANCE_LOCK
    lock, _INSTANCE_LOCK = _INSTANCE_LOCK, None
    if lock is not None:
        lock.release()


def _update_gate_allows_start() -> bool:
    """Paso 2: un actualizador en curso o una actualización que requiere
    recuperación impiden abrir la base. Devuelve False cuando hay que salir."""
    if PATHS is None:
        return True
    from backend.application.software_updates.startup_gate import (
        GateKind,
        UpdateStartupGate,
    )
    from backend.infrastructure.runtime.instance_lock import InstanceLock
    from backend.infrastructure.updater.update_job_store import UpdateJobStore

    store = UpdateJobStore(PATHS.update_job_path)
    gate = UpdateStartupGate(store, InstanceLock(PATHS.updater_lock_path)).inspect()
    if gate.kind is GateKind.CLEAR:
        if gate.message:
            logger.warning(gate.message)
        return True
    if gate.kind is GateKind.IN_PROGRESS:
        QMessageBox.information(None, f"Actualizando {APP_NAME}", gate.message)
        return False
    return _offer_guided_recovery(gate.job, store)


def _offer_guided_recovery(job, store) -> bool:
    """La reversión automática no terminó. Opciones reales: recuperar (el
    actualizador externo restaura el respaldo previo y reinstala la versión
    anterior) o salir. Abrir sin recuperar no se ofrece: la base puede estar
    a medio migrar."""
    detalle = (
        f"La actualización de {job.from_version} a {job.to_version} no terminó y la "
        "reversión automática tampoco.\n\n"
        f"{job.last_detail}\n\n"
        f"Respaldo previo: {job.backup_path or 'no se llegó a crear'}\n"
        f"Instalador de la versión anterior: {job.previous_installer_path or 'no disponible'}\n\n"
        "«Recuperar» restaura la base de datos al momento previo a la actualización y "
        "reinstala la versión anterior (se pedirá autorización de administrador)."
    )
    box = QMessageBox(QMessageBox.Critical, f"Recuperación — {APP_NAME}", detalle)
    recuperar = box.addButton("Recuperar", QMessageBox.AcceptRole)
    box.addButton("Salir", QMessageBox.RejectRole)
    box.exec_()
    if box.clickedButton() is not recuperar:
        return False
    try:
        from backend.application.software_updates.installation import SoftwareInstallation
        from backend.infrastructure.updater.update_launcher import ExternalUpdaterLauncher

        ExternalUpdaterLauncher(SoftwareInstallation.describe(PATHS)).launch(
            job_path=store.path, wait_pid=os.getpid(), mode="recover")
    except Exception as exc:
        logger.exception("No se pudo iniciar la recuperación")
        QMessageBox.critical(None, "Recuperación",
                             f"No se pudo iniciar el actualizador: {exc}")
    return False


def _relocate_legacy_database() -> bool:
    """Paso 4. False cuando el arranque debe detenerse."""
    if PATHS is None or str(PATHS.database_path) != DB_PATH:
        return True  # ruta fijada a mano (pruebas, soporte)
    from backend.infrastructure.db.database_relocation import (
        LegacyDatabaseRelocator,
        RelocationStatus,
    )

    result = LegacyDatabaseRelocator(PATHS).run()
    logger.info("Ubicación de la base: %s — %s", result.status.value, result.message)
    if result.blocks_startup:
        QMessageBox.critical(None, "Base de datos — no se abrió", result.message)
        return False
    if result.status is RelocationStatus.RELOCATED:
        QMessageBox.information(None, "Base de datos trasladada", result.message)
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


def _record_station_start(connection) -> None:
    """Paso 6: inventario de versión de la estación y resultado de la última
    actualización (que el actualizador dejó en su diario, fuera de la base)."""
    if PATHS is None:
        return
    try:
        from backend.application.software_updates.use_cases import RecordStationStartUseCase
        from backend.infrastructure.desktop.software_updates_factory import (
            build_software_update_dependencies,
        )

        notice = RecordStationStartUseCase(
            build_software_update_dependencies(connection, paths=PATHS)).execute()
    except Exception:
        # El inventario de versiones no debe impedir vender.
        logger.exception("No se pudo registrar la versión de la estación.")
        return
    if notice is not None:
        QMessageBox.information(None, notice.title, notice.message)


def _build_services():
    from backend.bootstrap.composition_root import CompositionRoot
    from backend.bootstrap.wiring.database_wiring import DatabaseModuleProvider
    from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider
    from backend.bootstrap.wiring.shared_wiring import SharedModuleProvider

    return CompositionRoot([
        SharedModuleProvider(), SecurityModuleProvider(), DatabaseModuleProvider(),
    ]).build()


def _logout_and_reauthenticate(app, window, coordinator) -> bool:
    """Discard session-owned widgets and rebuild them only after a fresh login."""
    try:
        coordinator.logout(window.router.current_context.session_id)
    except Exception:
        logger.exception("No se pudo revocar la sesión")
        QMessageBox.critical(window, "Cerrar sesión", "No se pudo cerrar la sesión. Intente nuevamente.")
        return False
    quit_on_close = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    try:
        window.setEnabled(False)
        window.hide()
        if window.service_supervisor is not None:
            window.service_supervisor.stop_all()
        window.deleteLater()
        accepted = coordinator.run()
        if not accepted:
            app.quit()
        return accepted
    except Exception:
        logger.exception("Falló la reapertura del login tras cerrar sesión")
        app.quit()
        return False
    finally:
        app.setQuitOnLastWindowClosed(quit_on_close)


def _make_update_handoff(app, connection, ventana: dict):
    """Cierre ordenado para instalar: servicios de fondo, conexiones, candado
    y, sólo entonces, el actualizador externo. Si el actualizador no arranca,
    la aplicación sigue abierta y nada cambió."""

    def handoff(launch_request) -> bool:
        from backend.application.software_updates.installation import SoftwareInstallation
        from backend.infrastructure.updater.update_launcher import ExternalUpdaterLauncher

        window = ventana.get("window")
        try:
            command = ExternalUpdaterLauncher(SoftwareInstallation.describe(PATHS))
        except Exception as exc:
            QMessageBox.critical(window, "Actualización", f"No se pudo preparar el actualizador: {exc}")
            return False
        if window is not None and window.service_supervisor is not None:
            window.service_supervisor.stop_all()
        from backend.infrastructure.db.sqlite_backup import checkpoint_wal

        if not checkpoint_wal(connection):
            logger.warning("No se pudo consolidar el WAL antes de actualizar.")
        try:
            command.launch(job_path=launch_request.job_path, wait_pid=os.getpid())
        except Exception as exc:
            logger.exception("No se pudo iniciar el actualizador")
            QMessageBox.critical(window, "Actualización",
                                 f"No se pudo iniciar el actualizador: {exc}\n\nNo se cambió nada.")
            if window is not None and window.service_supervisor is not None:
                window.service_supervisor.start_all()
            return False
        logger.info("Cerrando para instalar la versión %s.", launch_request.job.to_version)
        try:
            from backend.infrastructure.db.connection import close_thread_connection

            close_thread_connection()
            connection.close()
        except Exception:
            pass
        _release_instance_lock()
        app.quit()
        return True

    return handoff


def main() -> int:
    """Arranca la aplicación. Devuelve el código de salida del proceso."""
    if "--self-test" in sys.argv:
        from backend.bootstrap.self_test import main as self_test_main

        return self_test_main()

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

    if _PATHS_ERROR is not None:
        QMessageBox.critical(
            None, f"Instalación dañada — {APP_NAME}",
            f"{_PATHS_ERROR}\n\nRepare la instalación desde «Aplicaciones instaladas» de "
            "Windows. No se abrió ninguna base de datos.")
        return 1

    from frontend.desktop.components.branding import BrandAssetProvider
    BrandAssetProvider.apply_to_application(app)

    try:
        from frontend.desktop.themes.theme_manager import ThemeManager

        ThemeManager.instance().restore(app)
    except Exception as exc:
        logger.warning("No se pudo aplicar el tema guardado: %s", exc)

    if not _update_gate_allows_start():
        return 0

    if not _acquire_instance_lock():
        QMessageBox.information(
            None, "Ya está ejecutándose",
            f"{APP_NAME} ya está abierto en esta computadora.")
        return 0

    if not _relocate_legacy_database():
        return 1

    bootstrap = _prepare_database()
    connection = bootstrap.context.conn
    _record_station_start(connection)
    services = _build_services()

    from backend.bootstrap.wiring.event_wiring import wire_cross_context_events

    try:
        wire_cross_context_events(connection)
    except Exception:
        # Un cableado fallido no debe tumbar el arranque: los use cases que
        # publican directamente (ventas→inventario, ventas→caja) siguen
        # funcionando sin el bus; se pierde la integración entre contextos,
        # no la operación local.
        logger.exception("No se pudo cablear la integración entre contextos.")

    ventana = {}

    from frontend.desktop.shell.application_lifecycle import set_update_handoff

    set_update_handoff(_make_update_handoff(app, connection, ventana))

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
        window.logout_requested.connect(lambda: _logout_and_reauthenticate(app, window, coordinator))
        if window.sidebar is not None and window.sidebar.active_route:
            window.navigate(window.sidebar.active_route)
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
    set_update_handoff(None)
    _release_instance_lock()
    logger.info("Sistema cerrado. Código: %s", exit_code)
    return exit_code
