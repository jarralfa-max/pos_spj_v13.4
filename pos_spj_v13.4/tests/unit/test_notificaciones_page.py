"""SET-20 cutover — `NotificacionesPage` widget smoke tests, against the
REAL `create_configuracion_view()` factory and real (in-memory) SQLite —
mirrors the "verified end-to-end through the real factory" discipline
every prior Configuración CRUD round in this track used.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.application.use_cases.configuracion.notification_management_use_cases import (  # noqa: E402
    CreateNotificationAccountUseCase,
    CreateNotificationTemplateUseCase,
)
from backend.domain.notifications.enums import NotificationChannel  # noqa: E402
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


class TestNotificacionesPageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_notificaciones")
        page = view._pages["config_notificaciones"]

        assert page.accounts_table.accessibleName() == "Cuentas de notificación"
        assert page.templates_table.accessibleName() == "Plantillas de notificación"

    def test_route_and_account_and_template_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_notificaciones")
        page = view._pages["config_notificaciones"]

        assert page.new_route_button.text() == "Nueva ruta"
        assert page.new_account_button.text() == "Nueva cuenta"
        assert page.new_template_button.text() == "Nueva plantilla"


class TestNotificacionesPageLoadsRealData:
    def test_accounts_table_loads_real_accounts(self, app, conn):
        CreateNotificationAccountUseCase(conn).execute(channel=NotificationChannel.WHATSAPP, name="WA principal")

        view = _view(app, conn)
        view.show_route("config_notificaciones")
        page = view._pages["config_notificaciones"]

        assert page.accounts_table.rowCount() == 1

    def test_templates_table_loads_real_templates(self, app, conn):
        CreateNotificationTemplateUseCase(conn).execute(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX")

        view = _view(app, conn)
        view.show_route("config_notificaciones")
        page = view._pages["config_notificaciones"]

        assert page.templates_table.rowCount() == 1

    def test_route_created_through_the_real_presenter_appears_in_the_main_table(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_notificaciones")
        page = view._pages["config_notificaciones"]
        presenter = page._presenter

        account = CreateNotificationAccountUseCase(conn).execute(
            channel=NotificationChannel.WHATSAPP, name="WA principal")
        template = CreateNotificationTemplateUseCase(conn).execute(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX")
        ok, message = presenter.create_notification_route(
            event_code="pedido_confirmado", channel="WHATSAPP", template_id=template.id, account_id=account.id)
        assert ok is True, message

        page.reload()
        assert page.table.rowCount() == 1
