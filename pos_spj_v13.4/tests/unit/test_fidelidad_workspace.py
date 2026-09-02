"""LOY-25 — FidelidadWorkspace routing/capability-gating tests (mirrors
``tests/unit/test_customers_crm_ui_workspace.py``'s approach)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from frontend.desktop.modules.fidelidad.fidelidad_presenter import FidelidadPresenter
from frontend.desktop.modules.fidelidad.fidelidad_routes import FIDELIDAD_ROUTES
from frontend.desktop.modules.fidelidad.fidelidad_workspace import FidelidadWorkspace


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
        presenter = FidelidadPresenter(session_context=_AllowAllSession())
        workspace = FidelidadWorkspace(presenter)
        assert set(workspace._route_index_by_id) == {r.route_id for r in FIDELIDAD_ROUTES}
        for route in FIDELIDAD_ROUTES:
            workspace.select_route(route.route_id)  # must not raise

    def test_no_permission_shows_a_single_no_permission_state(self, app):
        presenter = FidelidadPresenter(session_context=_DenyAllSession())
        workspace = FidelidadWorkspace(presenter)
        assert workspace._route_index_by_id == {}
        assert workspace._stack.count() == 1

    def test_real_pages_are_not_placeholders(self, app):
        """LOY-25 built real pages for these 6 routes — a regression that
        silently downgraded one to the generic placeholder would still let
        `select_route` pass, so check page type identity instead."""
        from frontend.desktop.components.view_states import StateWidget
        presenter = FidelidadPresenter(session_context=_AllowAllSession())
        workspace = FidelidadWorkspace(presenter)
        real_routes = (
            "fidelidad.overview", "loyalty.programs", "loyalty.member_profile",
            "loyalty.rewards", "instruments.coupons", "instruments.vouchers",
            "sweepstakes.campaigns",
        )
        for route_id in real_routes:
            workspace.select_route(route_id)
            host = workspace._stack.currentWidget()
            scroll = host.findChild(QtWidgets.QScrollArea)
            page = scroll.widget()
            assert not isinstance(page, StateWidget), f"{route_id} is still a placeholder"
