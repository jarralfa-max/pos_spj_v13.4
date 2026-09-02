"""SET-18 cutover — `PantallaClientePage` widget smoke tests, against
the REAL `create_configuracion_view()` factory and real (in-memory)
SQLite — mirrors the "verified end-to-end through the real factory"
discipline every prior Configuración CRUD round in this track used.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.application.use_cases.configuracion.customer_display_advertising_use_cases import (  # noqa: E402
    ContentCampaignStatusAction,
    CreateAdvertisingSlotUseCase,
    CreateContentCampaignUseCase,
    CreateContentUseCase,
)
from backend.domain.customer_display.enums import ContentType, CustomerDisplayMode  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    create_configuracion_view,
)
from tests.integration._born_clean_db import make_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=()) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self.active_branch_id = "branch-1"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions

    def es_admin(self) -> bool:
        return False


def _all_permissions() -> set:
    return {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)}


def _view(app, conn):
    class _FakeContainer:
        db = conn
        session = _FakeSession(_all_permissions())

    return create_configuracion_view(_FakeContainer())


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestPantallaClientePageStructure:
    def test_builds_via_the_real_route_and_shows_all_four_cards(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        assert page.content_table.accessibleName() == "Contenido de publicidad"
        assert page.campaigns_table.accessibleName() == "Campañas de contenido"
        assert page.slots_table.accessibleName() == "Slots publicitarios"
        assert page.placements_table.accessibleName() == "Asignaciones de campañas a slots"

    def test_campaign_lifecycle_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        assert page.submit_campaign_button.text() == "Enviar a aprobación"
        assert page.approve_campaign_button.text() == "Aprobar"
        assert page.reject_campaign_button.text() == "Rechazar"
        assert page.activate_campaign_button.text() == "Activar"
        assert page.deactivate_campaign_button.text() == "Desactivar"
        assert page.expire_campaign_button.text() == "Expirar"
        assert page.archive_campaign_button.text() == "Archivar"


class TestPantallaClientePageLoadsRealData:
    def test_content_table_loads_real_content(self, app, conn):
        CreateContentUseCase(conn).execute(title="Promo", content_type=ContentType.TEXT, body="2x1")

        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        assert page.content_table.rowCount() == 1

    def test_campaigns_table_loads_real_campaigns(self, app, conn):
        content = CreateContentUseCase(conn).execute(
            title="Promo", content_type=ContentType.TEXT, body="2x1")
        CreateContentCampaignUseCase(conn).execute(name="Verano", content_id=content.id)

        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        assert page.campaigns_table.rowCount() == 1

    def test_slots_table_loads_real_slots(self, app, conn):
        CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)

        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        assert page.slots_table.rowCount() == 1

    def test_new_content_via_the_real_dialog_values_persists(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]

        ok, _message = page._presenter.create_display_content(
            title="Promo", content_type="TEXT", body="2x1", duration_seconds=5)
        assert ok is True
        page._reload_content()
        assert page.content_table.rowCount() == 1

    def test_full_campaign_lifecycle_through_the_real_presenter(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_pantalla_cliente")
        page = view._pages["config_pantalla_cliente"]
        presenter = page._presenter

        ok, _ = presenter.create_display_content(title="Promo", content_type="TEXT", body="2x1")
        content_id = presenter.list_display_content()[0].entity_id
        ok, _ = presenter.create_content_campaign(name="Verano", content_id=content_id)
        campaign_id = presenter.list_content_campaigns()[0].entity_id

        ok, _ = presenter.change_content_campaign_status(
            campaign_id=campaign_id, action="SUBMIT_FOR_APPROVAL")
        assert ok is True
        presenter._session.user_id = new_uuid()  # a different actor must approve (§59 segregation)
        ok, msg = presenter.change_content_campaign_status(campaign_id=campaign_id, action="APPROVE")
        assert ok is True, msg
        ok, msg = presenter.change_content_campaign_status(campaign_id=campaign_id, action="ACTIVATE")
        assert ok is True, msg
        assert presenter.list_content_campaigns()[0].status == "ACTIVE"
