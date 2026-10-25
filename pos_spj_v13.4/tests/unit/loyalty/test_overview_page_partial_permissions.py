"""FID-08 (auditoría de Fidelidad 968e0bc): con `VIEW` pero sin
`DASHBOARD_VIEW`, el Resumen explica qué falta en lugar de mostrar un error."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    return qt.QApplication.instance() or qt.QApplication([])


class _Presenter:
    def __init__(self, permisos):
        self._permisos = set(permisos)
        self.llamadas = []

    def can(self, codigo):
        return codigo in self._permisos

    def overview(self):
        self.llamadas.append("overview")
        raise PermissionError("sin GROWTH_ENGINE.dashboard.ver")

    def alerts(self):
        self.llamadas.append("alerts")
        return []


def test_a_view_only_role_sees_an_explanation_not_an_error(app):
    from backend.application.loyalty.permissions import LoyaltyPermissions
    from frontend.desktop.components.view_states import ViewState
    from frontend.desktop.modules.fidelidad.pages.overview_page import FidelidadOverviewPage

    presenter = _Presenter({LoyaltyPermissions.VIEW})
    page = FidelidadOverviewPage(presenter)
    page.reload()
    assert presenter.llamadas == []          # ni siquiera pide lo que no puede ver
    assert page._status.property("state") == ViewState.NO_PERMISSION
    assert "no ver los indicadores" in page._status.text()
