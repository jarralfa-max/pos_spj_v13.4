"""LOY-25 — TarjetasFidelidadWorkspace routing/capability-gating tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_presenter import (
    TarjetasFidelidadPresenter,
)
from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_routes import (
    TARJETAS_FIDELIDAD_ROUTES,
)
from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_workspace import (
    TarjetasFidelidadWorkspace,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _AllowAllSession:
    user_id = "u1"
    active_branch_id = "b1"

    def tiene_permiso(self, _permission: str) -> bool:
        return True


class _DenyAllSession:
    user_id = "u1"
    active_branch_id = "b1"

    def tiene_permiso(self, _permission: str) -> bool:
        return False


class TestWorkspaceRouting:
    def test_every_route_gets_a_working_page(self, app):
        presenter = TarjetasFidelidadPresenter(session_context=_AllowAllSession())
        workspace = TarjetasFidelidadWorkspace(presenter)
        assert set(workspace._route_index_by_id) == {
            r.route_id for r in TARJETAS_FIDELIDAD_ROUTES}
        for route in TARJETAS_FIDELIDAD_ROUTES:
            workspace.select_route(route.route_id)  # must not raise

    def test_no_permission_shows_a_single_no_permission_state(self, app):
        presenter = TarjetasFidelidadPresenter(session_context=_DenyAllSession())
        workspace = TarjetasFidelidadWorkspace(presenter)
        assert workspace._route_index_by_id == {}
        assert workspace._stack.count() == 1

    def test_real_pages_are_not_placeholders(self, app):
        from frontend.desktop.components.view_states import StateWidget
        presenter = TarjetasFidelidadPresenter(session_context=_AllowAllSession())
        workspace = TarjetasFidelidadWorkspace(presenter)
        for route_id in ("tarjetas.overview", "tarjetas.cards", "tarjetas.templates"):
            workspace.select_route(route_id)
            host = workspace._stack.currentWidget()
            scroll = host.findChild(QtWidgets.QScrollArea)
            page = scroll.widget()
            assert not isinstance(page, StateWidget), f"{route_id} is still a placeholder"
