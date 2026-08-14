"""The customers_crm composition root, wired into the real app for the
first time: proves the whole chain (session checker → scope resolvers →
query services → presenter → workspace) actually constructs against a real
connection, which no test exercised end-to-end before this phase — every
prior customers_crm test used fakes for query_services/command_handlers.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.customers.permissions import CustomerPermissions
from backend.shared.ids import new_uuid


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, grants=(), *, is_active=True, user_id="u1", active_branch_id="b1"):
        self._grants = set(grants)
        self.is_active = is_active
        self.user_id = user_id
        self.active_branch_id = active_branch_id

    def tiene_permiso(self, code):
        return code in self._grants


class TestBuildCustomersCrmPresenter:
    def test_constructs_with_a_real_session(self, full_crm_conn):
        from frontend.desktop.modules.customers_crm.composition import (
            build_customers_crm_presenter,
        )

        session = _FakeSession({CustomerPermissions.VIEW})
        presenter = build_customers_crm_presenter(full_crm_conn, session)
        assert presenter.current_user_id() == "u1"
        # Every query service the workspace/pages rely on must be present.
        for key in ("dashboard", "customers_directory", "leads_directory",
                    "opportunities_directory", "cases_directory", "customer_360"):
            assert presenter.query_service(key) is not None
        assert presenter.command_handler("create_customer") is not None
        assert presenter.command_handler("update_customer") is not None

    def test_constructs_with_no_session_at_all(self, full_crm_conn):
        """Composition must not raise just because no user is logged in yet
        (e.g. app startup before login) — only individual calls fail closed."""
        from frontend.desktop.modules.customers_crm.composition import (
            build_customers_crm_presenter,
        )

        presenter = build_customers_crm_presenter(full_crm_conn, None)
        assert presenter.current_user_id() == ""

    def test_dashboard_call_degrades_when_permission_denied(self, full_crm_conn):
        from frontend.desktop.modules.customers_crm.composition import (
            build_customers_crm_presenter,
        )

        session = _FakeSession(grants=())  # no CustomerPermissions.VIEW
        presenter = build_customers_crm_presenter(full_crm_conn, session)
        # Fails closed (real PermissionChecker denies), never raises to the caller.
        view = presenter.dashboard()
        assert view is not None

    def test_create_then_update_customer_round_trip(self, full_crm_conn):
        from frontend.desktop.modules.customers_crm.composition import (
            build_customers_crm_presenter,
        )

        session = _FakeSession({CustomerPermissions.VIEW, CustomerPermissions.CREATE,
                                CustomerPermissions.EDIT, CustomerPermissions.VIEW_COMPANY})
        presenter = build_customers_crm_presenter(full_crm_conn, session)

        created = presenter.create_customer(
            display_name="Restaurante El Sol", customer_type="BUSINESS")
        assert created.success is True

        updated = presenter.update_customer(
            created.entity_id, display_name="Restaurante El Sol (renombrado)")
        assert updated.success is True

        view = presenter.customer_360(created.entity_id)
        assert view.profile.customer.display_name == "Restaurante El Sol (renombrado)"


class TestCreateCustomersCrmView:
    def test_builds_a_real_workspace(self, app, full_crm_conn):
        from frontend.desktop.modules.customers_crm.composition import (
            create_customers_crm_view,
        )
        from frontend.desktop.modules.customers_crm.customers_crm_workspace import (
            CustomersCrmWorkspace,
        )

        session = _FakeSession({CustomerPermissions.VIEW})
        view = create_customers_crm_view(full_crm_conn, session)
        assert isinstance(view, CustomersCrmWorkspace)
        view.deleteLater()
        app.processEvents()


class TestModuloClientesCrmShim:
    def test_unwraps_container_and_builds_view(self, app, full_crm_conn):
        """modulos/clientes_crm.py — the legacy-navigation-compatible entry
        point interfaz/main_window.py calls. Verifies the container is
        unwrapped to the real `.db`/`.session` attributes (not the finance
        module's apparently-nonexistent `.session_context`)."""
        from modulos.clientes_crm import ModuloClientesCrm

        class _FakeContainer:
            db = full_crm_conn
            session = _FakeSession({CustomerPermissions.VIEW})

        view = ModuloClientesCrm(_FakeContainer())
        from frontend.desktop.modules.customers_crm.customers_crm_workspace import (
            CustomersCrmWorkspace,
        )
        assert isinstance(view, CustomersCrmWorkspace)
        view.deleteLater()
        app.processEvents()
