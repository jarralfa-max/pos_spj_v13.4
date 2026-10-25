"""Contenedores 2026-10-17: códigos automáticos, selección, etiqueta QR y
lectura con la cámara del teléfono.

Hallazgos que fijan estas pruebas:
* el código se tecleaba (la base real tenía «CAJ-0001» y «CAJ-001»);
* en «Compra en origen» no había forma de ELEGIR un contenedor (sólo teclear);
* la etiqueta sólo salía por una térmica enrutada: sin ella no había etiqueta,
  ni PDF, ni vista previa;
* el QR se validaba recalculando el HMAC con el secreto del almacén de Windows,
  que es POR USUARIO: el servicio de la API (otra cuenta) rechazaba etiquetas
  legítimas impresas desde el escritorio;
* la PWA sólo escaneaba con `BarcodeDetector` (no existe en Safari/iPhone ni
  Firefox) y su captura manual pedía el «token», no el código impreso.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest

from backend.application.logistics.authorization import (
    LogisticsAuthorizationPolicy,
    LogisticsPermissions,
)
from backend.application.logistics.container_catalog import ContainerCatalogService
from backend.application.logistics.container_labels import ContainerLabelService
from backend.application.logistics.queries import LogisticsContainerQueryService
from backend.application.logistics.service import LogisticsApplicationService
from backend.domain.logistics.container_codes import next_code
from backend.domain.logistics.exceptions import LogisticsDomainError
from backend.domain.logistics.labels import ContainerLabelContent, ContainerLabelFormat
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.infrastructure.printing import container_label_renderer as renderer
from backend.infrastructure.printing.container_label_renderer import (
    ReportlabContainerLabelRenderer,
)

ROOT = Path(__file__).parents[3]


class _Perms:
    def has_permission(self, user_id, permission):
        return True


class _Printer:
    def __init__(self):
        self.jobs = []

    def submit(self, job, payload):
        self.jobs.append((job, payload))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    path = ROOT / "migrations/standalone/171_logistics_bounded_context_schema.py"
    spec = importlib.util.spec_from_file_location("m171", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run(c)
    yield c
    c.close()


def _service(conn, secret=b"a" * 32, printer=None):
    return LogisticsApplicationService(conn, LogisticsAuthorizationPolicy(_Perms()),
                                       PermanentContainerQrService(secret), printer)


def _type(conn, app, category="PLASTIC_BOX", name="Caja azul"):
    return ContainerCatalogService(app, conn).register_container_type(
        actor_user_id="u", code=name.upper().replace(" ", "-"), name=name, category=category,
        tare_weight="2")


def _labels(conn, app):
    return ContainerLabelService(app, LogisticsContainerQueryService(conn),
                                 ReportlabContainerLabelRenderer())


# ── códigos automáticos ─────────────────────────────────────────────────────
def test_codes_are_assigned_by_the_system_per_category_and_in_batches(conn):
    app = _service(conn)
    catalog = ContainerCatalogService(app, conn)
    caja, tarima = _type(conn, app), _type(conn, app, "PALLET", "Tarima")
    assert catalog.next_code_preview(caja) == "CJ-000001"
    uno = catalog.register_container(actor_user_id="u", container_type_id=caja)
    lote = catalog.register_container(actor_user_id="u", container_type_id=caja, quantity=3)
    otra = catalog.register_container(actor_user_id="u", container_type_id=tarima)
    assert uno["code"] == "CJ-000001"
    assert lote["codes"] == ["CJ-000002", "CJ-000003", "CJ-000004"]
    assert otra["code"] == "TR-000001"
    assert catalog.next_code_preview(category="PLASTIC_BOX") == "CJ-000005"
    # cada uno nace con su QR y la tara del tipo
    fila = conn.execute("SELECT tare_weight, qr_signature FROM logistics_physical_containers"
                        " WHERE container_code='CJ-000003'").fetchone()
    assert fila[0] == "2" and fila[1]


def test_manual_codes_are_kept_and_numbering_skips_taken_numbers(conn):
    assert next_code("CJ", ["CAJ-0001", "CJ-000007", "cj-000002", "CJ-ABC"]) == "CJ-000008"
    app = _service(conn)
    catalog = ContainerCatalogService(app, conn)
    caja = _type(conn, app)
    conn.execute("INSERT INTO logistics_physical_containers (id, container_code,"
                 " container_type_id, tare_weight, owner_type, status, condition, qr_version,"
                 " created_at) VALUES ('legacy', 'CJ-000041', ?, '1', 'COMPANY', 'AVAILABLE',"
                 " 'GOOD', 1, 'x')", (caja,))
    assert catalog.register_container(actor_user_id="u",
                                      container_type_id=caja)["code"] == "CJ-000042"


def test_batch_limits_and_serial_only_for_one(conn):
    app = _service(conn)
    catalog = ContainerCatalogService(app, conn)
    caja = _type(conn, app)
    with pytest.raises(ValueError, match="entre 1 y 500"):
        catalog.register_container(actor_user_id="u", container_type_id=caja, quantity=0)
    with pytest.raises(ValueError, match="de uno en uno"):
        catalog.register_container(actor_user_id="u", container_type_id=caja, quantity=2,
                                   serial_number="S-1")


# ── QR: validable desde cualquier proceso ───────────────────────────────────
def test_a_label_issued_on_the_desktop_validates_in_the_api_process(conn):
    """El servicio de la API corre con OTRA cuenta de Windows (otro secreto)."""
    escritorio, api = _service(conn, b"a" * 32), _service(conn, b"z" * 32)
    caja = _type(conn, escritorio)
    cid = ContainerCatalogService(escritorio, conn).register_container(
        actor_user_id="u", container_type_id=caja)["container_id"]
    token = escritorio.label_token(cid)
    assert api.find_container(token).id == cid
    assert api.find_container("cj-000001").id == cid            # el código impreso también
    falsificado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(LogisticsDomainError):
        api.find_container(falsificado)
    contenedor = escritorio.get_container(cid)
    contenedor.rotate_qr()
    escritorio._qr.issue(contenedor)
    with conn:
        escritorio._repo.save_container(contenedor)
    with pytest.raises(LogisticsDomainError):                 # la etiqueta vieja ya no vale
        api.find_container(token)


def test_compact_payload_fits_alphanumeric_qr_and_old_labels_still_read(conn):
    app = _service(conn)
    cid = ContainerCatalogService(app, conn).register_container(
        actor_user_id="u", container_type_id=_type(conn, app))["container_id"]
    token = app.label_token(cid)
    assert token.startswith("SPJC/") and re.fullmatch(r"[0-9A-Z $%*+\-./:]+", token)
    assert len(renderer.qr_matrix(token)) <= 41               # versión 4 con zona de silencio
    # formato anterior: URL con dominio y id en minúsculas
    container = app.get_container(cid)
    viejo = f"https://app.spj.mx/c/{cid}.{container.qr_version}.{container.qr_signature}"
    assert app.find_container(viejo).id == cid


def test_unprinted_long_signature_is_reissued_but_a_printed_one_is_kept(conn):
    app = _service(conn, printer=_Printer())
    caja = _type(conn, app)
    ids = ContainerCatalogService(app, conn).register_container(
        actor_user_id="u", container_type_id=caja, quantity=2)["container_ids"]
    largo = "x" * 43     # firma base64 de antes de 2026-10-17
    conn.execute("UPDATE logistics_physical_containers SET qr_signature=?", (largo,))
    # ids[1] ya tenía etiqueta impresa con la firma larga (antes del cambio)
    conn.execute("INSERT INTO logistics_container_labels VALUES"
                 " ('l-viejo', ?, NULL, 'PERMANENT_QR', 1, 'x', 'ACTIVE', 'x', 'op-viejo')",
                 (ids[1],))
    app.create_label_and_print(actor_user_id="u", container_id=ids[1], printer_id="routed",
                               operation_id="op-print")
    assert app.get_container(ids[1]).qr_signature == largo   # ya impresa: no cambia
    assert app.label_token(ids[0]) != f"SPJC/{ids[0].upper()}.1.{largo}"
    assert PermanentContainerQrService.is_compact_signature(app.get_container(ids[0]).qr_signature)


# ── etiqueta: PDF, vista previa, térmica ────────────────────────────────────
def test_pdf_formats_audit_and_reprint_reason(conn):
    app = _service(conn)
    caja = _type(conn, app)
    ids = ContainerCatalogService(app, conn).register_container(
        actor_user_id="u", container_type_id=caja, quantity=6)["container_ids"]
    labels = _labels(conn, app)
    pdf = labels.export_pdf(actor_user_id="u", container_ids=ids[:3],
                            fmt=ContainerLabelFormat.LABEL_100X50, copies=2)
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 6
    hoja = labels.export_pdf(actor_user_id="u", container_ids=ids[3:], fmt="SHEET_LETTER_2X5",
                             copies=4)                          # 12 etiquetas → 2 hojas
    assert hoja.startswith(b"%PDF")
    trabajos = conn.execute("SELECT printer_id, status, copies FROM logistics_print_jobs"
                            " ORDER BY printer_id").fetchall()
    assert len(trabajos) == 6 and {t[1] for t in trabajos} == {"COMPLETED"}
    assert {t[0] for t in trabajos} == {"PDF:LABEL_100X50", "PDF:SHEET_LETTER_2X5"}
    with pytest.raises(ValueError, match="motivo de la reimpresión"):
        labels.export_pdf(actor_user_id="u", container_ids=ids[:1], fmt="LABEL_50X30")
    assert labels.export_pdf(actor_user_id="u", container_ids=ids[:1], fmt="LABEL_50X30",
                             reprint_reason="Se mojó").startswith(b"%PDF")
    motivo = conn.execute("SELECT reprint_reason FROM logistics_print_jobs"
                          " WHERE printer_id='PDF:LABEL_50X30'").fetchone()[0]
    assert motivo == "Se mojó"
    # el QR impreso es el MISMO en cada reimpresión
    tokens = {r[0] for r in conn.execute(
        "SELECT token FROM logistics_container_labels WHERE container_id=?", (ids[0],))}
    assert len(tokens) == 1


def test_the_pdf_draws_exactly_the_qr_matrix():
    """El PDF dibuja la misma matriz que el lector de la PWA decodifica abajo."""
    payload = "SPJC/01A14A4E-CE11-7F82-80B7-1881EF9F22EC.1.OKAOCQAL5I5LEJYNWPPJM22Q4I"

    class _Canvas:
        def __init__(self):
            self.rects = []

        def setFillColorRGB(self, *_):
            pass

        def rect(self, x, y, w, h, stroke=0, fill=1):
            self.rects.append((x, y))

    lienzo = _Canvas()
    renderer._draw_qr_pdf(lienzo, payload, 0, 0, 41.0)
    matriz = renderer.qr_matrix(payload)
    assert len(lienzo.rects) == sum(sum(fila) for fila in matriz)


def _content(payload="SPJC/01A14A4E-CE11-7F82-80B7-1881EF9F22EC.1.OKAOCQAL5I5LEJYNWPPJM22Q4I"):
    return ContainerLabelContent("id", "CJ-000123", "Caja de 40 kg", "Caja plástica", "2.000",
                                 "40.000", "Carnes SPJ", payload, 1)


def test_thermal_escpos_carries_code_details_and_raster_qr():
    datos = renderer.render_escpos(_content(), paper_mm=80, copies=2)
    assert datos.count(b"CJ-000123") == 2 and b"Tara 2.000 kg" in datos
    assert b"\x1dv0" in datos                                # imagen rasterizada (el QR)


def test_preview_decodes_with_the_same_reader_the_phone_uses(tmp_path):
    """jsQR (el lector de la PWA sin BarcodeDetector) dentro de QtWebEngine, en
    un proceso aparte. Resoluciones bajas, como una foto tomada de lejos."""
    pytest.importorskip("PyQt5.QtWebEngineWidgets")
    import subprocess
    import sys

    contenido = _content()
    imagenes = []
    for fmt, px in ((ContainerLabelFormat.LABEL_100X50, 4), (ContainerLabelFormat.LABEL_50X30, 3),
                    (ContainerLabelFormat.LABEL_50X30, 8)):
        ruta = tmp_path / f"{fmt.value}_{px}.png"
        ruta.write_bytes(renderer.render_preview_png(contenido, fmt, px_per_mm=px))
        imagenes.append(str(ruta))
    import os
    # QtWebEngine truena con la plataforma «offscreen»; la página nunca se muestra.
    entorno = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    salida = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("_jsqr_decode.py")),
         str(ROOT / "frontend/web/logistics/vendor/jsQR.js"), *imagenes],
        capture_output=True, text=True, timeout=240, env=entorno)
    if salida.returncode not in (0,) and not salida.stdout.strip():
        pytest.skip(f"QtWebEngine no disponible en este entorno (código {salida.returncode})")
    leidos = [linea for linea in salida.stdout.splitlines() if linea.strip()]
    assert leidos == [contenido.qr_payload] * len(imagenes), salida.stderr[-2000:]


# ── teléfono: código impreso o QR ───────────────────────────────────────────
def test_mobile_workflow_resolves_and_attaches_by_printed_code_or_qr(conn, tmp_path):
    from backend.api.mobile_session import MobileIdentity
    from backend.api.service_host import FilePhotoGateway
    from backend.application.logistics.mobile_workflow import MobileOriginPurchaseWorkflow

    escritorio, api = _service(conn, b"a" * 32), _service(conn, b"z" * 32)
    cid = ContainerCatalogService(escritorio, conn).register_container(
        actor_user_id="u", container_type_id=_type(conn, escritorio))["container_id"]
    flujo = MobileOriginPurchaseWorkflow(conn, api, api._qr, FilePhotoGateway(tmp_path))
    yo = MobileIdentity("u", "U", "b", "B", "w", "W", "tel",
                        (LogisticsPermissions.CONTAINER_SCAN,))
    assert flujo.resolve_container(yo, escritorio.label_token(cid))["containerCode"] == "CJ-000001"
    assert flujo.resolve_container(yo, "cj-000001")["containerId"] == cid
    with pytest.raises(ValueError, match="No existe"):
        flujo.resolve_container(yo, "CJ-999999")


def test_api_answers_rule_violations_with_their_reason_and_accepts_short_codes():
    from fastapi.testclient import TestClient

    from backend.api.main import create_app
    from backend.api.mobile_session import MobileIdentity, MobileSessionTokenService

    class _Verifier:
        def authenticate_mobile(self, username, password, device_id):
            return MobileIdentity("u", "U", "b", "B", "w", "W", device_id,
                                  (LogisticsPermissions.CONTAINER_SCAN,))

    class _Flujo:
        def resolve_container(self, identity, token):
            if token == "CJ-000001":
                return {"containerId": "c", "containerCode": token, "typeName": "Caja"}
            raise ValueError(f"No existe el contenedor {token}")

    app = create_app()
    app.state.mobile_session_service = MobileSessionTokenService(b"m" * 32, _Verifier())
    app.state.origin_purchase_workflow = _Flujo()
    api = TestClient(app)
    token = api.post("/api/mobile/session", json={"username": "a", "password": "b",
                                                  "deviceId": "t"}).json()["accessToken"]
    cabeza = {"Authorization": f"Bearer {token}"}
    ok = api.get("/api/logistics/containers/resolve?token=CJ-000001", headers=cabeza)
    assert ok.status_code == 200 and ok.json()["containerCode"] == "CJ-000001"
    malo = api.get("/api/logistics/containers/resolve?token=CJ-9", headers=cabeza)
    assert malo.status_code == 400 and "No existe" in malo.json()["detail"]
    assert api.get("/", follow_redirects=False).headers["location"] == "/mobile/logistics/"


def test_pwa_scans_without_barcode_detector_and_takes_the_printed_code():
    app_js = (ROOT / "frontend/web/logistics/app.js").read_text(encoding="utf-8")
    html = (ROOT / "frontend/web/logistics/index.html").read_text(encoding="utf-8")
    sw = (ROOT / "frontend/web/logistics/sw.js").read_text(encoding="utf-8")
    assert "vendor/jsQR.js" in app_js and "isSecureContext" in app_js
    assert "vendor/jsQR.js" in sw                       # también sin conexión
    assert "Código impreso" in html and "continuousScan" in html
    assert "Token seguro" not in html


def test_pwa_loads_without_javascript_errors_in_an_old_browser():
    """Sin Node en el equipo, esto es lo que detecta un error de sintaxis en la
    PWA (pasó con `||=`, que Chromium 83 / Safari 13 no entienden)."""
    pytest.importorskip("PyQt5.QtWebEngineWidgets")
    import os
    import socket
    import subprocess
    import sys

    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
    entorno = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    salida = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("_pwa_console.py")), str(puerto)],
        capture_output=True, text=True, timeout=120, env=entorno)
    lineas = [x for x in salida.stdout.splitlines() if x.strip()]
    if salida.returncode != 0 and not lineas:
        pytest.skip(f"QtWebEngine no disponible en este entorno (código {salida.returncode})")
    assert lineas == ["OK"], " | ".join(lineas) + salida.stderr[-1500:]


# ── HTTPS para la cámara ────────────────────────────────────────────────────
def test_lan_bind_gets_a_self_signed_certificate_covering_its_ip(tmp_path):
    from cryptography import x509

    from backend.api import service_host

    cert, key = service_host.ensure_self_signed_certificate("192.168.1.20", tmp_path)
    leido = x509.load_pem_x509_certificate(cert.read_bytes())
    san = leido.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "192.168.1.20" in {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    assert key.exists()
    antes = cert.read_bytes()
    service_host.ensure_self_signed_certificate("192.168.1.20", tmp_path)
    assert cert.read_bytes() == antes                   # se reutiliza
    service_host.ensure_self_signed_certificate("192.168.1.30", tmp_path)
    assert cert.read_bytes() != antes                   # otra IP: se regenera
    assert service_host.tls_files({"SPJ_API_BIND_HOST": "127.0.0.1",
                                   "SPJ_API_PORT": "8765"}) == (None, None)


# ── escritorio ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_qt():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_register_dialog_has_no_code_field_and_shows_the_next_code(app_qt):
    from frontend.desktop.modules.purchasing.dialogs.origin_dialogs import (
        ContainerRegisterDialog,
    )
    pedidos = []

    def vista_previa(type_id, category):
        pedidos.append((type_id, category))
        return "CJ-000007"

    dialogo = ContainerRegisterDialog(type_options=[("t1", "Caja azul (Caja plástica)")],
                                      code_preview=vista_previa)
    dialogo._type.set_current_id("t1")
    dialogo._quantity.setValue(3)
    assert "3 códigos a partir de CJ-000007" in dialogo._code.text()
    valores = dialogo.container_values()
    assert "code" not in valores and valores["quantity"] == 3
    assert not dialogo._serial.isEnabled()              # serie sólo para uno


def test_containers_page_multi_select_and_label_dialog(app_qt, conn):
    from frontend.desktop.modules.logistics.dialogs import ContainerLabelDialog
    from frontend.desktop.modules.logistics.logistics_presenter import LogisticsPresenter
    from frontend.desktop.modules.logistics.pages import ContainersPage

    app = _service(conn)
    catalog = ContainerCatalogService(app, conn)
    ids = catalog.register_container(actor_user_id="u", container_type_id=_type(conn, app),
                                     quantity=3)["container_ids"]

    class _Sesion:
        user_id = "u"

        def tiene_permiso(self, code):
            return True

    presenter = LogisticsPresenter(queries=LogisticsContainerQueryService(conn), catalog=catalog,
                                   session_context=_Sesion(), labels=_labels(conn, app))
    page = ContainersPage(presenter)
    page.refresh()
    page.table.selectAll()
    assert sorted(page.table.selected_row_ids()) == sorted(ids)
    dialogo = ContainerLabelDialog(
        codes=["CJ-000001"], formats=presenter.label_formats(),
        preview=lambda fmt: presenter.label_preview(ids[0], fmt), reprinted=["CJ-000001"])
    assert dialogo.image.pixmap() is not None and not dialogo.image.pixmap().isNull()
    assert dialogo.problem() == "Captura el motivo de la reimpresión."
    dialogo.reason.setText("rota")
    assert dialogo.problem() is None


def test_origin_page_lists_containers_to_pick():
    pagina = (ROOT / "frontend/desktop/modules/purchasing/pages/logistics_related_page.py"
              ).read_text(encoding="utf-8")
    assert "SearchSelector(" in pagina and "origin_container_options" in pagina
    assert "submitted.connect(self._attach_scanned)" in pagina   # lector de QR/teclado
