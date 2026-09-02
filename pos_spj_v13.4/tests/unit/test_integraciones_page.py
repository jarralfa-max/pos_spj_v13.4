"""SET-19 cutover — `IntegracionesPage` widget smoke tests, against the
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
from backend.application.use_cases.configuracion.integration_management_use_cases import (  # noqa: E402
    CreateIntegrationDefinitionUseCase,
    CreateIntegrationInstanceUseCase,
    SetIntegrationInstanceCredentialUseCase,
)
from backend.domain.integrations.enums import IntegrationCategory  # noqa: E402
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


class TestIntegracionesPageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_integraciones")
        page = view._pages["config_integraciones"]

        assert page.instances_table.accessibleName() == "Instancias de la definición seleccionada"
        assert page.webhooks_table.accessibleName() == "Webhooks de la instancia seleccionada"
        assert page.health_table.accessibleName() == "Historial de chequeos de la instancia seleccionada"

    def test_definition_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_integraciones")
        page = view._pages["config_integraciones"]

        assert page.new_definition_button.text() == "Nueva definición"
        assert page.edit_definition_button.text() == "Editar definición"
        assert page.activate_definition_button.text() == "Activar definición"
        assert page.deactivate_definition_button.text() == "Desactivar definición"


class TestIntegracionesPageSelectionCascade:
    def _seed(self, conn) -> tuple[str, str]:
        definition = CreateIntegrationDefinitionUseCase(conn).execute(
            code="MERCADOPAGO", name="MercadoPago", category=IntegrationCategory.PAYMENTS,
            required_credential_names=("mp_access_token",),
        )
        instance = CreateIntegrationInstanceUseCase(conn).execute(
            definition_id=definition.id, name="MercadoPago prod")
        return definition.id, instance.id

    def test_selecting_a_definition_loads_its_instances(self, app, conn):
        self._seed(conn)
        view = _view(app, conn)
        view.show_route("config_integraciones")
        page = view._pages["config_integraciones"]
        page.reload()

        assert page.table.rowCount() == 1
        page.table.selectRow(0)

        assert page.instances_table.rowCount() == 1

    def test_selecting_an_instance_loads_credentials_webhooks_and_health(self, app, conn):
        definition_id, instance_id = self._seed(conn)
        SetIntegrationInstanceCredentialUseCase(conn, _FakeSecretStore()).execute(
            instance_id=instance_id, credential_name="mp_access_token", secret_name="mp_access_token",
            secret_value="fake-value",
        )
        view = _view(app, conn)
        view.show_route("config_integraciones")
        page = view._pages["config_integraciones"]
        page.reload()
        page.table.selectRow(0)
        page.instances_table.selectRow(0)

        assert page.credentials_table.rowCount() == 1
        status_text = page.credentials_table.item(0, 1).text()
        assert "fake-value" not in status_text  # never the raw secret, only masked
        assert "Configurada" in status_text


class _FakeSecretStore:
    def set_secret(self, name, value):
        pass
