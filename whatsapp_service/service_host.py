"""Production host of the OPTIONAL local WhatsApp service (`spj_whatsapp.exe`).

Replaces `start_all.bat` for installed stations: no `--reload`, no source
tree, a single worker, bound to loopback unless the station explicitly asks
for more, logs and configuration in the data folder (never in the files the
installer replaces). The recommended production profile is a REMOTE WhatsApp
service; the desktop never starts this one on its own.

    spj_whatsapp.exe run                      foreground (diagnostics)
    spj_whatsapp.exe install|start|stop|remove|restart
                                              Windows service "SPJWhatsApp"
                                              (pywin32 service framework; the
                                              installer runs these elevated)

Configuration — `<datos>/whatsapp/whatsapp.env` (loaded by
`whatsapp_service.config.settings`):

    WA_BIND_HOST=127.0.0.1   # 0.0.0.0 only behind a reverse proxy/tunnel
    WA_PORT=8000
    WA_ACCESS_TOKEN=... WA_VERIFY_TOKEN=... WA_APP_SECRET=... (secrets)

The service needs the MACHINE data scope: as LocalSystem it cannot see a
per-user data folder; the installer only offers the component then.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import sys

SERVICE_NAME = "SPJWhatsApp"
SERVICE_DISPLAY_NAME = "SPJ — Servicio WhatsApp local"
SERVICE_DESCRIPTION = ("Canal WhatsApp de SPJ ERP/POS para esta estación. Opcional: en "
                       "producción se recomienda el servicio remoto.")


def _ensure_import_path() -> None:
    package_root = Path(__file__).resolve().parents[1] / "pos_spj_v13.4"
    if package_root.is_dir() and str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def _configure_logging() -> None:
    _ensure_import_path()
    from backend.shared.app_paths import AppPaths

    paths = AppPaths.from_environment()
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.whatsapp_data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(paths.logs_dir / "whatsapp_service.log"), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8")


def build_server():
    """A uvicorn server for the ASGI app — never with reload."""
    _ensure_import_path()
    import uvicorn

    from whatsapp_service.main import app  # loads settings (and whatsapp.env)

    host = os.environ.get("WA_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("WA_PORT", "8000"))
    config = uvicorn.Config(app, host=host, port=port, reload=False, workers=1,
                            log_config=None, access_log=False)
    return uvicorn.Server(config)


def run_foreground() -> int:
    _configure_logging()
    server = build_server()
    logging.getLogger("spj.whatsapp.host").info(
        "Servicio WhatsApp en %s:%s", server.config.host, server.config.port)
    server.run()
    return 0


def _windows_service_class():
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class SPJWhatsAppService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args) -> None:
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._server = None

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._server is not None:
                self._server.should_exit = True
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self) -> None:
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} iniciando")
            _configure_logging()
            self._server = build_server()
            self._server.run()
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} detenido")

    return SPJWhatsAppService


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    command = argv[1] if len(argv) > 1 else ""
    if command == "run":
        return run_foreground()
    if sys.platform != "win32":
        print("Uso: spj_whatsapp run", file=sys.stderr)
        return 2
    import servicemanager
    import win32serviceutil

    service_class = _windows_service_class()
    if not command:
        # Started by the Service Control Manager.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(service_class)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    win32serviceutil.HandleCommandLine(service_class, argv=argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
