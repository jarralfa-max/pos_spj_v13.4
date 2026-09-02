"""SET-22 repegado — `AparienciaPage` widget smoke tests, against the
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
from backend.application.use_cases.configuracion.appearance_management_use_cases import (  # noqa: E402
    CreateDensityProfileUseCase,
    CreateThemeUseCase,
)
from backend.domain.appearance.enums import DensityLevel, ThemeMode  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from decimal import Decimal  # noqa: E402
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


class TestAparienciaPageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]

        assert page.table.accessibleName() == "Listado de Apariencia"
        assert page.tokens_table.accessibleName() == "Tokens de diseño del tema seleccionado"
        assert page.density_table.accessibleName() == "Perfiles de densidad"
        assert page.preferences_table.accessibleName() == "Preferencias de apariencia por alcance"

    def test_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]

        assert page.new_theme_button.text() == "Nuevo tema"
        assert page.new_token_button.text() == "Nuevo token"
        assert page.new_density_button.text() == "Nuevo perfil"
        assert page.new_preference_button.text() == "Nueva preferencia"


class TestAparienciaPageLoadsRealData:
    def test_themes_table_loads_all_themes_including_inactive(self, app, conn):
        CreateThemeUseCase(conn).execute(code="claro", name="Claro", mode=ThemeMode.LIGHT)
        inactive = CreateThemeUseCase(conn).execute(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        inactive.deactivate()
        from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository
        SqliteThemeRepository(conn).save(inactive)
        conn.commit()

        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]

        assert page.table.rowCount() == 2

    def test_selecting_a_theme_loads_its_tokens(self, app, conn):
        theme = CreateThemeUseCase(conn).execute(code="claro", name="Claro", mode=ThemeMode.LIGHT)

        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]
        presenter = page._presenter

        ok, message = presenter.create_design_token(
            theme_id=theme.id, token_key="color.background", category="COLOR", token_value="#FFFFFF")
        assert ok is True, message

        page.reload()
        page.table.selectRow(0)
        assert page.tokens_table.rowCount() == 1

    def test_density_profiles_table_loads_real_profiles(self, app, conn):
        CreateDensityProfileUseCase(conn).execute(
            level=DensityLevel.NORMAL, name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
            touch_target_px=44, spacing_unit_px=8,
        )

        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]

        assert page.density_table.rowCount() == 1


class TestAparienciaFullLoop:
    def test_create_theme_token_density_and_preference(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_apariencia")
        page = view._pages["config_apariencia"]
        presenter = page._presenter

        ok, message = presenter.create_theme(code="claro", name="Claro", mode="LIGHT")
        assert ok is True, message
        theme = presenter.list_themes()[0]

        ok, message = presenter.create_design_token(
            theme_id=None, token_key="spacing.md", category="SPACING", token_value="16px")
        assert ok is True, message

        ok, message = presenter.create_density_profile(
            level="NORMAL", name="Normal", scale_factor=Decimal("1.0"), control_height_px=36,
            touch_target_px=44, spacing_unit_px=8,
        )
        assert ok is True, message

        ok, message = presenter.create_appearance_preference(
            scope_type="GLOBAL", scope_id=None, theme_id=theme.entity_id, density_level="NORMAL")
        assert ok is True, message

        page.reload()
        page.table.selectRow(0)
        assert page.table.rowCount() == 1
        assert page.tokens_table.rowCount() == 1
        assert page.density_table.rowCount() == 1
        assert page.preferences_table.rowCount() == 1
