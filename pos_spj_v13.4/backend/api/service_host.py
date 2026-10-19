"""Host de producción del servicio OPCIONAL API + PWA de Logística
(`spj_api.exe`, integración Logística 32cfbf; decisión del usuario).

`create_app()` sólo monta rutas: sin sesión móvil ni flujo inyectados la API
respondía 503 y nada la hospedaba en una instalación. Este host arma la app con
la composición real (base de datos de la estación, secreto persistente, login
contra los usuarios reales, autorización por rol del usuario que opera) y la
sirve con uvicorn, sin recarga y con un solo proceso.

    spj_api.exe run                         primer plano (diagnóstico)
    spj_api.exe install|start|stop|remove   servicio de Windows «SPJMobileAPI»

Configuración — `<datos>/mobile_api/mobile_api.env` (no la reemplaza el instalador):

    SPJ_API_BIND_HOST=127.0.0.1   # por omisión sólo esta máquina; la IP de la red
                                  # local para teléfonos, nunca 0.0.0.0 por omisión
    SPJ_API_PORT=8765
    SPJ_API_SSL_CERTFILE=...      # certificado propio (recomendado: uno que los
    SPJ_API_SSL_KEYFILE=...       # teléfonos confíen, p. ej. de una CA local)

Fuera de loopback la API SIEMPRE atiende por HTTPS: el navegador del teléfono
sólo abre la cámara (escanear el QR de la etiqueta) en una conexión segura. Si
no se configura certificado, se genera uno autofirmado para la IP configurada
en `<datos>/mobile_api/tls/`; el teléfono lo acepta una vez («Avanzado →
Continuar»). Con certificado autofirmado la PWA funciona y escanea, pero el
modo sin conexión (service worker) exige un certificado de confianza.

No hay credenciales por omisión: se entra con usuario y clave del ERP y el
permiso `LOGISTICA.embarque.ver`. El secreto de los tokens se genera una vez y
vive en el almacén de secretos (cambiarlo cierra todas las sesiones móviles).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import secrets
import sys

SERVICE_NAME = "SPJMobileAPI"
SERVICE_DISPLAY_NAME = "SPJ — API y PWA de Logística"
SERVICE_DESCRIPTION = ("Carga en origen desde el teléfono (PWA) de SPJ ERP/POS. Opcional; "
                       "sólo atiende en la red configurada.")
SESSION_SECRET_KEY = "mobile_api.session_secret"
DEFAULT_PORT = 8765
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

logger = logging.getLogger("spj.api.host")


def _ensure_import_path() -> None:
    package_root = Path(__file__).resolve().parents[2]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


def _paths():
    from backend.shared.app_paths import AppPaths
    return AppPaths.from_environment()


def config_dir() -> Path:
    return _paths().user_data_dir / "mobile_api"


def load_settings(env_file: Path | None = None) -> dict[str, str]:
    """Variables del archivo de la estación; el entorno del proceso manda sobre él."""
    valores: dict[str, str] = {}
    archivo = env_file or (config_dir() / "mobile_api.env")
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip()
    for clave in ("SPJ_API_BIND_HOST", "SPJ_API_PORT", "SPJ_API_SSL_CERTFILE",
                  "SPJ_API_SSL_KEYFILE"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    valores.setdefault("SPJ_API_BIND_HOST", "127.0.0.1")
    valores.setdefault("SPJ_API_PORT", str(DEFAULT_PORT))
    return valores


def session_secret(secret_store) -> bytes:
    """Secreto HMAC de los tokens móviles: se genera UNA vez por instalación."""
    valor = secret_store.get_secret(SESSION_SECRET_KEY)
    if valor and len(valor) >= 64:
        return bytes.fromhex(valor)
    valor = secrets.token_hex(32)
    secret_store.set_secret(SESSION_SECRET_KEY, valor)
    return bytes.fromhex(valor)


class FilePhotoGateway:
    """Fotos de la carga en `<datos>/logistics_photos/`; devuelve el id guardado."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def save(self, *, content: bytes, file_name: str, content_type: str,
             actor_user_id: str, operation_id: str) -> str:
        from backend.shared.ids import new_uuid
        self._folder.mkdir(parents=True, exist_ok=True)
        extension = {"image/jpeg": ".jpg", "image/png": ".png",
                     "image/webp": ".webp"}.get(content_type, ".bin")
        photo_id = new_uuid()
        (self._folder / f"{photo_id}{extension}").write_bytes(content)
        return photo_id


def build_app(connection=None, *, secret_store=None, photos_dir: Path | None = None):
    """La app FastAPI con la composición real inyectada en `app.state`."""
    _ensure_import_path()
    from backend.api.main import create_app
    from backend.api.mobile_credentials import DatabaseMobileCredentialVerifier
    from backend.api.mobile_session import MobileSessionTokenService
    from backend.application.logistics.authorization import LogisticsAuthorizationPolicy
    from backend.application.logistics.composition import qr_signing_secret
    from backend.application.logistics.mobile_workflow import MobileOriginPurchaseWorkflow
    from backend.application.logistics.service import LogisticsApplicationService
    from backend.application.security.authorizer_permission_checker import (
        AuthorizerPermissionChecker,
    )
    from backend.domain.logistics.qr_identity import PermanentContainerQrService

    if connection is None:
        from backend.infrastructure.db.database import (
            DatabaseSettings,
            create_connection_factory,
        )
        # La MISMA base que el escritorio; compartida entre los hilos de FastAPI
        # porque el middleware de abajo serializa las solicitudes.
        connection = create_connection_factory(
            DatabaseSettings.sqlite(_paths()), check_same_thread=False)()
        connection.execute("PRAGMA foreign_keys=ON")
    if secret_store is None:
        from backend.security.secrets.default_secret_store import build_default_secret_store
        secret_store = build_default_secret_store()
    qr = PermanentContainerQrService(qr_signing_secret(secret_store))
    # Autoriza por el ROL del usuario que opera desde el teléfono (no hay sesión
    # de escritorio en este proceso).
    logistics = LogisticsApplicationService(
        connection, LogisticsAuthorizationPolicy(AuthorizerPermissionChecker(connection)), qr)
    app = create_app()
    # Una sola conexión SQLite para todo el proceso, y FastAPI atiende las rutas
    # síncronas desde un pool de hilos: sin serializar, dos teléfonos a la vez
    # intercalarían sus transacciones. El volumen es de unos cuantos teléfonos.
    one_at_a_time = asyncio.Lock()

    @app.middleware("http")
    async def _serialize_requests(request, call_next):
        async with one_at_a_time:
            return await call_next(request)

    app.state.mobile_session_service = MobileSessionTokenService(
        session_secret(secret_store), DatabaseMobileCredentialVerifier(connection))
    app.state.origin_purchase_workflow = MobileOriginPurchaseWorkflow(
        connection, logistics, qr,
        FilePhotoGateway(photos_dir or (_paths().user_data_dir / "logistics_photos")))
    return app


def ensure_self_signed_certificate(host: str, folder: Path | None = None) -> tuple[Path, Path]:
    """Certificado autofirmado (RSA 2048, 2 años) con la IP/nombre de `host` en
    el SAN. Se reutiliza mientras exista y cubra ese host."""
    import datetime
    import ipaddress
    import socket

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    carpeta = folder or (config_dir() / "tls")
    cert_path, key_path = carpeta / "spj_api_cert.pem", carpeta / "spj_api_key.pem"
    nombres = {host} if host not in ("0.0.0.0", "::") else set()
    nombres.add(socket.gethostname())
    if cert_path.exists() and key_path.exists():
        try:
            actual = x509.load_pem_x509_certificate(cert_path.read_bytes())
            san = actual.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            cubiertos = {str(v) for v in san.get_values_for_type(x509.IPAddress)}
            cubiertos |= set(san.get_values_for_type(x509.DNSName))
            vigente = actual.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc)
            if vigente and nombres <= cubiertos:
                return cert_path, key_path
        except Exception:  # noqa: BLE001 - ilegible: se regenera
            logger.warning("certificado de la API ilegible; se regenera")
    carpeta.mkdir(parents=True, exist_ok=True)
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    alternos = []
    for nombre in sorted(nombres):
        try:
            alternos.append(x509.IPAddress(ipaddress.ip_address(nombre)))
        except ValueError:
            alternos.append(x509.DNSName(nombre))
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SPJ API de Logística"),
                        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SPJ ERP/POS")])
    ahora = datetime.datetime.now(datetime.timezone.utc)
    certificado = (x509.CertificateBuilder().subject_name(sujeto).issuer_name(sujeto)
                   .public_key(clave.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(ahora - datetime.timedelta(minutes=5))
                   .not_valid_after(ahora + datetime.timedelta(days=730))
                   .add_extension(x509.SubjectAlternativeName(alternos), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .sign(clave, hashes.SHA256()))
    key_path.write_bytes(clave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    cert_path.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    huella = certificado.fingerprint(hashes.SHA256()).hex(":").upper()
    logger.info("Certificado autofirmado de la API generado para %s (SHA-256 %s)",
                ", ".join(sorted(nombres)), huella)
    return cert_path, key_path


def tls_files(cfg: dict[str, str]) -> tuple[str | None, str | None]:
    """Certificado configurado; fuera de loopback, uno autofirmado si no hay."""
    certfile, keyfile = cfg.get("SPJ_API_SSL_CERTFILE"), cfg.get("SPJ_API_SSL_KEYFILE")
    if certfile:
        return certfile, keyfile or None
    if cfg["SPJ_API_BIND_HOST"] in _LOOPBACK:
        return None, None
    cert, key = ensure_self_signed_certificate(cfg["SPJ_API_BIND_HOST"])
    return str(cert), str(key)


def public_url(cfg: dict[str, str]) -> str:
    """La dirección que se teclea en el teléfono."""
    host = cfg["SPJ_API_BIND_HOST"]
    esquema = "https" if tls_files(cfg)[0] else "http"
    return f"{esquema}://{host}:{cfg['SPJ_API_PORT']}/mobile/logistics/"


def build_server(settings: dict[str, str] | None = None):
    _ensure_import_path()
    import uvicorn

    cfg = settings or load_settings()
    host, port = cfg["SPJ_API_BIND_HOST"], int(cfg["SPJ_API_PORT"])
    if host == "0.0.0.0":
        logger.warning("La API escucha en TODAS las interfaces: hágalo sólo detrás de un "
                       "proxy con TLS.")
    certfile, keyfile = tls_files(cfg)
    if certfile:
        logger.info("PWA de Logística en %s", public_url(cfg))
    config = uvicorn.Config(
        build_app(), host=host, port=port, reload=False, workers=1, log_config=None,
        access_log=False, ssl_certfile=certfile, ssl_keyfile=keyfile)
    return uvicorn.Server(config)


def _configure_logging() -> None:
    _ensure_import_path()
    paths = _paths()
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir().mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(paths.logs_dir / "mobile_api.log"), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8")


def run_foreground() -> int:
    _configure_logging()
    server = build_server()
    logger.info("API de Logística en %s:%s", server.config.host, server.config.port)
    server.run()
    return 0


def _windows_service_class():
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class SPJMobileAPIService(win32serviceutil.ServiceFramework):
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

    return SPJMobileAPIService


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    command = argv[1] if len(argv) > 1 else ""
    if command == "run":
        return run_foreground()
    if sys.platform != "win32":
        print("Uso: spj_api run", file=sys.stderr)
        return 2
    import servicemanager
    import win32serviceutil

    service_class = _windows_service_class()
    if not command:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(service_class)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    win32serviceutil.HandleCommandLine(service_class, argv=argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
