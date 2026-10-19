"""Integración Logística 32cfbf: catálogo de contenedores, segregación
despacho≠recepción, identidades sin `uuid5`/concatenación, módulo de escritorio
y capacidad instalable `logistics`."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from backend.application.logistics.authorization import (
    LogisticsAuthorizationPolicy,
    LogisticsPermissionDeniedError,
    LogisticsPermissions,
)
from backend.application.logistics.container_catalog import ContainerCatalogService
from backend.application.logistics.queries import LogisticsContainerQueryService
from backend.application.logistics.service import LogisticsApplicationService
from backend.domain.logistics.entities import LogisticsShipment
from backend.domain.logistics.enums import SourceDocumentType
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.domain.software_distribution.install_profile import (
    EnabledCapabilities,
    InstallProfile,
)
from backend.shared.ids import new_uuid

ROOT = Path(__file__).parents[3]


class _Perms:
    def __init__(self, denied=()):
        self.denied = set(denied)

    def has_permission(self, user_id, permission):
        return permission not in self.denied


class _Printer:
    def __init__(self):
        self.jobs = []

    def submit(self, job, payload):
        self.jobs.append((job, payload))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    for version in ("171_logistics_bounded_context_schema",):
        path = ROOT / f"migrations/standalone/{version}.py"
        spec = importlib.util.spec_from_file_location(version, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.run(c)
    yield c
    c.close()


def _service(conn, *, denied=(), printer=None):
    return LogisticsApplicationService(
        conn, LogisticsAuthorizationPolicy(_Perms(denied)),
        PermanentContainerQrService(b"q" * 32), printer)


def _container(conn, app):
    catalog = ContainerCatalogService(app, conn)
    type_id = catalog.register_container_type(
        actor_user_id="u", code="CAJA", name="Caja azul", category="PLASTIC_BOX")
    return catalog, catalog.register_container(
        actor_user_id="u", container_type_id=type_id)["container_id"]


def test_catalog_registers_without_a_shipment_and_explains_loadability(conn):
    app = _service(conn)
    catalog, cid = _container(conn, app)
    q = LogisticsContainerQueryService(conn)
    (fila,) = q.containers()
    assert fila["code"] == "CJ-000001" and fila["loadable"] and fila["status_label"] == "Disponible"
    catalog.update_container(actor_user_id="u", container_id=cid, tare_weight="1.5",
                             capacity_weight="20", serial_number="S-9", location_id="Andén 2")
    catalog.set_status(actor_user_id="u", container_id=cid, status="CLEANING",
                       reason="Lavado semanal")
    (fila,) = q.containers()
    assert not fila["loadable"] and fila["not_loadable_reason"] == "En limpieza"
    assert fila["tare_weight"] == "1.5" and fila["location_id"] == "Andén 2"
    acciones = [h["action"] for h in q.history(cid)]
    assert "STATUS AVAILABLE->CLEANING" in acciones and "UPDATED" in acciones


def test_status_needs_a_reason_and_not_while_travelling(conn):
    app = _service(conn)
    catalog, cid = _container(conn, app)
    with pytest.raises(ValueError):
        catalog.set_status(actor_user_id="u", container_id=cid, status="MAINTENANCE", reason=" ")
    envio = LogisticsShipment.create(
        shipment_number="E-1", origin_type="SUPPLIER", origin_location="A",
        destination_branch_id="b", destination_warehouse_id="w", buyer_user_id="u",
        operation_id=new_uuid())
    envio.add_source(SourceDocumentType.PURCHASE_ORDER, "po-1")
    app.create_shipment(actor_user_id="u", shipment=envio)
    app.attach_container(actor_user_id="u", shipment_id=envio.id, container_id=cid,
                         operation_id=new_uuid())
    with pytest.raises(ValueError, match="embarque activo"):
        catalog.set_status(actor_user_id="u", container_id=cid, status="MAINTENANCE",
                           reason="Golpe")
    (fila,) = LogisticsContainerQueryService(conn).containers()
    assert fila["not_loadable_reason"] == "En el embarque E-1"


def test_thermal_label_goes_through_the_printer_gateway(conn):
    from backend.application.logistics.container_labels import ContainerLabelService
    from backend.infrastructure.printing.container_label_renderer import (
        ReportlabContainerLabelRenderer,
    )
    printer = _Printer()
    app = _service(conn, printer=printer)
    _catalog, cid = _container(conn, app)
    labels = ContainerLabelService(app, LogisticsContainerQueryService(conn),
                                   ReportlabContainerLabelRenderer())
    assert labels.print_thermal(actor_user_id="u", container_ids=[cid]) == 1
    with pytest.raises(ValueError, match="motivo"):          # ya se imprimió: reimpresión
        labels.print_thermal(actor_user_id="u", container_ids=[cid])
    labels.print_thermal(actor_user_id="u", container_ids=[cid], reprint_reason="Etiqueta rota")
    assert len(printer.jobs) == 2 and printer.jobs[1][0].reprint_reason == "Etiqueta rota"


def test_container_manage_permission_is_enforced(conn):
    app = _service(conn, denied={LogisticsPermissions.CONTAINER_MANAGE})
    with pytest.raises(LogisticsPermissionDeniedError):
        ContainerCatalogService(app, conn).register_container_type(
            actor_user_id="u", code="X", name="X", category="TOTE")


def _dispatched(conn, app, cid, dispatcher):
    envio = LogisticsShipment.create(
        shipment_number="E-2", origin_type="SUPPLIER", origin_location="A",
        destination_branch_id="b", destination_warehouse_id="w", buyer_user_id=dispatcher,
        operation_id=new_uuid())
    envio.add_source(SourceDocumentType.PURCHASE_ORDER, "po-1")
    app.create_shipment(actor_user_id=dispatcher, shipment=envio)
    nodo = app.attach_container(actor_user_id=dispatcher, shipment_id=envio.id,
                                container_id=cid, operation_id=new_uuid())
    app.seal(actor_user_id=dispatcher, shipment_id=envio.id, node_id=nodo.id,
             seal_code="S-1", seal_type="TAPE", operation_id=new_uuid())
    app.dispatch(actor_user_id=dispatcher, shipment_id=envio.id, operation_id=new_uuid())
    app.mark_in_transit(actor_user_id=dispatcher, shipment_id=envio.id, operation_id=new_uuid())
    return envio.id


def test_who_dispatched_cannot_register_the_arrival(conn):
    app = _service(conn, denied={LogisticsPermissions.SHIPMENT_OVERRIDE})
    _catalog, cid = _container(conn, app)
    envio = _dispatched(conn, app, cid, dispatcher="ana")
    with pytest.raises(LogisticsPermissionDeniedError, match="otra persona"):
        app.register_arrival(actor_user_id="ana", shipment_id=envio, operation_id=new_uuid())
    assert app.register_arrival(actor_user_id="beto", shipment_id=envio,
                                operation_id=new_uuid()).status.value == "ARRIVED"


def test_override_permission_allows_the_same_person(conn):
    app = _service(conn)
    _catalog, cid = _container(conn, app)
    envio = _dispatched(conn, app, cid, dispatcher="ana")
    assert app.register_arrival(actor_user_id="ana", shipment_id=envio,
                                operation_id=new_uuid()).status.value == "ARRIVED"


def test_no_derived_identities_remain_in_logistics():
    """Regla de identidad: sin `uuid5` ni operaciones armadas concatenando."""
    for path in (ROOT / "backend/application/logistics").glob("*.py"):
        texto = path.read_text(encoding="utf-8")
        assert "uuid.uuid5(" not in texto and "uuid5(" not in texto.replace("`uuid5`", ""), path.name
        assert 'f"{operation_id}:' not in texto, path.name


def test_receiving_a_shipment_twice_does_not_receive_the_document_twice():
    """La deduplicación es por clave de negocio (embarque, documento)."""
    from backend.application.logistics.origin_purchase_workspace import (
        OriginPurchaseWorkspaceService,
    )
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE goods_receipts (id TEXT, document_number TEXT, purchase_order_id TEXT,"
              " direct_purchase_id TEXT, shipment_id TEXT, status TEXT, created_at TEXT)")
    c.execute("INSERT INTO goods_receipts VALUES ('r1','REC-1','po-1',NULL,'sh-1','COMPLETED','x')")
    w = OriginPurchaseWorkspaceService(None, None, connection=c, supplier_origins=object(),
                                       product_catalog=object())
    assert w._receipt_of_shipment("sh-1", "PURCHASE_ORDER", "po-1") == "REC-1"
    assert w._receipt_of_shipment("sh-1", "PURCHASE_ORDER", "po-2") is None
    assert w._receipt_of_shipment("sh-2", "PURCHASE_ORDER", "po-1") is None


# ── capacidad instalable ────────────────────────────────────────────────────
def test_logistics_is_its_own_capability():
    erp = EnabledCapabilities.resolve(InstallProfile.ERP_FULL)
    assert erp.is_enabled("logistics")
    pos = EnabledCapabilities.resolve(InstallProfile.POS_ESSENTIAL)
    assert not pos.is_enabled("logistics")
    assert pos.permission_blocked("LOGISTICA.EMBARQUE.VER")
    solo_reparto = EnabledCapabilities.resolve(InstallProfile.CUSTOM, ["orders_delivery"])
    assert not solo_reparto.is_enabled("logistics")
    assert solo_reparto.permission_blocked("LOGISTICA.EMBARQUE.VER")
    assert not solo_reparto.permission_blocked("DELIVERY.VER")


def test_an_old_custom_install_keeps_logistics():
    """Catálogo 1: «Pedidos y entregas» incluía LOGISTICA; al actualizar no se pierde."""
    viejo = EnabledCapabilities.resolve(InstallProfile.CUSTOM, ["orders_delivery"],
                                        catalog_version=1)
    assert viejo.is_enabled("logistics")
    assert not viejo.permission_blocked("LOGISTICA.EMBARQUE.VER")


def test_install_config_reads_the_catalog_version():
    from backend.shared.install_config import InstallConfig
    base = {"format": "spj-install/1", "data_scope": "user", "profile": "custom",
            "capabilities": ["orders_delivery"]}
    assert InstallConfig.from_mapping(base).capability_catalog == 1
    assert InstallConfig.from_mapping({**base, "capability_catalog": 2}).capability_catalog == 2


def test_the_installer_offers_the_logistics_component():
    iss = (ROOT / "installer/windows/spj_setup.iss").read_text(encoding="utf-8")
    assert 'Name: "modulos\\logistics"' in iss
    assert "AddIfSelected(Result, 'logistics')" in iss
    assert '"capability_catalog": 2' in iss


# ── módulo de escritorio ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_qt():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_desktop_module_shows_containers_and_shipments(app_qt, conn):
    from frontend.desktop.modules.logistics.logistics_presenter import LogisticsPresenter
    from frontend.desktop.modules.logistics.logistics_view import LogisticsView
    from frontend.desktop.modules.logistics.pages import ContainersPage, ShipmentsPage

    app = _service(conn)
    _container(conn, app)

    class _Session:
        user_id, is_active = "u", True

        def tiene_permiso(self, code):
            return True

    presenter = LogisticsPresenter(queries=LogisticsContainerQueryService(conn),
                                   catalog=ContainerCatalogService(app, conn),
                                   session_context=_Session())
    paginas = {"lg_containers": lambda: ContainersPage(presenter),
               "lg_shipments": lambda: ShipmentsPage(presenter)}
    vista = LogisticsView(has_permission=lambda _c: True,
                          page_builder=lambda pid: paginas[pid]())
    contenedores = vista._pages["lg_containers"]
    assert contenedores.table.rowCount() == 1
    vista.show_route("lg_shipments")
    assert vista.stack.currentWidget() is vista._pages["lg_shipments"]


def test_logistics_is_registered_in_the_shell():
    from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
        MIGRATED_MODULES_NAVIGATION_ITEMS,
    )
    assert any(i.module_id == "logistics" for i in MIGRATED_MODULES_NAVIGATION_ITEMS)
    composicion = (ROOT / "frontend/desktop/shell/desktop_shell_window_composition.py").read_text(
        encoding="utf-8")
    assert "LogisticsModuleActivator" in composicion


def test_new_pickup_without_po_opens_the_shipment_from_the_direct_purchase(app_qt, monkeypatch):
    """«Nueva recolección sin orden de compra»: la compra directa se confirma por
    Compras con `SUPPLIER_PICKUP` y el embarque se abre desde ESA compra."""
    from PyQt5.QtCore import QTimer, pyqtSignal
    from PyQt5.QtWidgets import QWidget

    from frontend.desktop.components.dialogs import FormDialog
    from frontend.desktop.modules.purchasing.pages.logistics_related_page import (
        LogisticsRelatedPage,
    )

    documento = {"id": "dp-1", "document_number": "CD-1", "document_type": "DIRECT_PURCHASE",
                 "supplier_name": "Granja", "status": "CONFIRMED", "line_count": 1,
                 "shipment_id": None, "supplier_id": "s1",
                 "origin_supplier_address_id": "addr-1", "origin_display": "Bodega"}

    class _Presenter:
        def __init__(self):
            self.documents, self.created = [], []

        def origin_documents(self, search=""):
            return list(self.documents)

        def origin_create_shipment(self, document, origin_id=None):
            self.created.append(document["id"])
            return True, "", {"id": "sh-1", "nodes": [], "contents": [], "status": "PLANNED"}

        def __getattr__(self, name):          # el resto de la página no se usa aquí
            return lambda *a, **k: (True, "", {}) if name.startswith("origin_") else None

    class _CompraRapida(QWidget):
        purchase_confirmed = pyqtSignal(str, str)

        def start_pickup(self):
            presentador.documents.append(documento)      # Compras la deja CONFIRMADA
            QTimer.singleShot(0, lambda: self.purchase_confirmed.emit("dp-1", "SUPPLIER_PICKUP"))

    presentador = _Presenter()
    pagina = LogisticsRelatedPage(presentador, direct_purchase_factory=_CompraRapida)
    monkeypatch.setattr(pagina, "_render_detail", lambda detail: None)
    monkeypatch.setattr(FormDialog, "exec_", lambda self: (app_qt.processEvents(), 1)[1])
    assert pagina._new_pickup.isVisibleTo(pagina)
    pagina._start_direct_pickup()
    assert presentador.created == ["dp-1"]
