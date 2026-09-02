"""SET-21 repegado — `FeatureFlagsPage` widget smoke tests, against the
REAL `create_configuracion_view()` factory and real (in-memory) SQLite —
mirrors the "verified end-to-end through the real factory" discipline
every prior Configuración CRUD round in this track used. The last test
exercises the full Flags→Rules→Rollout→Approval loop for the first time
since SET-21 originally shipped (create → request → approve → apply).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.application.use_cases.configuracion.feature_flag_management_use_cases import (  # noqa: E402
    CreateFeatureFlagUseCase,
    RequestFeatureFlagChangeUseCase,
)
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    create_configuracion_view,
)
from tests.integration._born_clean_db import make_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=(), user_id=None) -> None:
        self.user_id = user_id or new_uuid()
        self.is_active = True
        self.active_branch_id = "branch-1"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions

    def es_admin(self) -> bool:
        return False


def _all_permissions() -> set:
    return {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)}


def _view(app, conn, *, user_id=None):
    class _FakeContainer:
        db = conn
        session = _FakeSession(_all_permissions(), user_id=user_id)

    return create_configuracion_view(_FakeContainer())


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestFeatureFlagsPageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]

        assert page.table.accessibleName() == "Listado de Feature Flags"
        assert page.rules_table.accessibleName() == "Reglas activas del flag seleccionado"
        assert page.requests_table.accessibleName() == "Solicitudes de cambio de feature flags pendientes"

    def test_flag_and_request_buttons_present(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]

        assert page.new_flag_button.text() == "Nueva flag"
        assert page.request_change_button.text() == "Solicitar cambio"
        assert page.approve_button.text() == "Aprobar"


class TestFeatureFlagsPageLoadsRealData:
    def test_flags_table_loads_all_flags_including_inactive(self, app, conn):
        CreateFeatureFlagUseCase(conn).execute(code="active_flag", name="Activo")
        inactive = CreateFeatureFlagUseCase(conn).execute(code="inactive_flag", name="Inactivo")
        inactive.deactivate()
        from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
            SqliteFeatureFlagRepository,
        )
        SqliteFeatureFlagRepository(conn).save(inactive)
        conn.commit()

        view = _view(app, conn)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]

        assert page.table.rowCount() == 2

    def test_selecting_a_flag_loads_its_rules(self, app, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f_rules", name="Con reglas")

        view = _view(app, conn)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]
        presenter = page._presenter

        ok, message = presenter.request_feature_flag_change(
            flag_id=flag.id, scope_type="GLOBAL", scope_id=None, proposed_enabled=True,
            proposed_rollout_percentage=100,
        )
        assert ok is True, message
        page._reload_requests()
        page.requests_table.selectRow(0)
        approver = _FakeSession(_all_permissions())
        # a second, different approver — segregation of duties (§59)
        presenter._session = approver
        ok, message = presenter.approve_feature_flag_change_request(page.requests_table.selected_row_id())
        assert ok is True, message
        ok, message = presenter.apply_feature_flag_change_request(page.requests_table.selected_row_id())
        assert ok is True, message

        page.reload()
        page.table.selectRow(0)
        assert page.rules_table.rowCount() == 1


class TestFeatureFlagsFullLoop:
    def test_create_request_approve_apply_closes_the_loop(self, app, conn):
        requester_id = new_uuid()
        view = _view(app, conn, user_id=requester_id)
        view.show_route("config_feature_flags")
        page = view._pages["config_feature_flags"]
        presenter = page._presenter

        ok, message = presenter.create_feature_flag(code="loop_flag", name="Loop", default_enabled=False)
        assert ok is True, message
        page.reload()
        assert page.table.rowCount() == 1

        flags = presenter.list_feature_flags()
        flag = flags[0]

        ok, message = presenter.request_feature_flag_change(
            flag_id=flag.entity_id, scope_type="GLOBAL", scope_id=None, proposed_enabled=True,
            proposed_rollout_percentage=50,
        )
        assert ok is True, message

        page._reload_requests()
        assert page.requests_table.rowCount() == 1

        # segregation of duties: the requester cannot approve their own request
        page.requests_table.selectRow(0)
        request_id = page.requests_table.selected_row_id()
        ok, message = presenter.approve_feature_flag_change_request(request_id)
        assert ok is False

        approver_session = _FakeSession(_all_permissions())
        presenter._session = approver_session
        ok, message = presenter.approve_feature_flag_change_request(request_id)
        assert ok is True, message

        ok, message = presenter.apply_feature_flag_change_request(request_id)
        assert ok is True, message

        page.reload()
        page.table.selectRow(0)
        assert page.rules_table.rowCount() == 1
        assert page.requests_table.rowCount() == 0


class TestSidebarPendingFlagRequestsBadge:
    """SET-24 repegado — the `pending_flag_requests` badge on the
    "Feature Flags" sidebar entry existed in the data model since the
    original UI/UX phase but was never computed/passed by either live
    construction path, so it never actually rendered a count. Closed
    now that SET-21's origination cutover makes a real pending count
    possible."""

    def test_no_badge_when_nothing_pending(self, app, conn):
        view = _view(app, conn)
        items = [view.sidebar.item(i) for i in range(view.sidebar.count())]
        labels = [item.text() for item in items]
        assert "Feature Flags" in labels

    def test_shows_real_pending_count(self, app, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="badge_flag", name="Badge")
        RequestFeatureFlagChangeUseCase(conn).execute(
            flag_id=flag.id, scope_type="GLOBAL", scope_id=None, proposed_enabled=True,
            requested_by_user_id=new_uuid(),
        )

        view = _view(app, conn)
        items = [view.sidebar.item(i) for i in range(view.sidebar.count())]
        labels = [item.text() for item in items]
        assert "Feature Flags (1)" in labels
