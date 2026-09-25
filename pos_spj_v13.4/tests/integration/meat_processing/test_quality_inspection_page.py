"""Calidad → Por inspeccionar: el inspector decide desde la pantalla.

Sin esta pantalla, lo retenido por inspección se quedaba retenido para siempre
(la ejecución ya no libera calidad). Aquí se prueba contra una planta real:
Calidad decide, Inventario pasa a disponible y Procesamiento lo registra por el
bus. La pantalla no muestra identidades.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.meat_processing.session_authorization import (
    MeatProcessingSessionPermissionChecker,
)
from backend.application.quality.output_inspection import (
    DecideOutputInspectionUseCase,
    QualityAuthorizationPolicy,
)
from backend.application.quality.permissions import QualityPermissions
from backend.domain.meat_processing.enums import OutputQualityStatus
from backend.shared.ids import is_uuidv7
from frontend.desktop.modules.meat_processing.presenters.quality_inspection_presenter import (
    QualityInspectionPresenter,
)
from tests.integration.meat_processing._quality_plant import PlantaConCalidad

QtWidgets = pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Sesion:
    is_active = True

    def __init__(self, user_id, branch_id, permisos):
        self.user_id, self.active_branch_id, self._permisos = user_id, branch_id, permisos

    def tiene_permiso(self, code):
        return code in self._permisos


def _presentador(planta, usuario, permisos):
    sesion = _Sesion(usuario, planta.p.branch, permisos)
    return QualityInspectionPresenter(
        planta.conn, branch_id=planta.p.branch, actor_provider=lambda: sesion.user_id,
        decide_uc=DecideOutputInspectionUseCase(QualityAuthorizationPolicy(
            MeatProcessingSessionPermissionChecker(sesion))),
        dispatch=planta.despachar)


@pytest.fixture()
def planta():
    q = PlantaConCalidad()
    yield q
    q.conn.close()


def test_the_pending_list_shows_what_is_held_by_its_code(planta):
    modelo = _presentador(planta, planta.p.inspector, set()).pending()
    assert modelo.rows == [["Filete de robalo", modelo.rows[0][1], "8 kg",
                            modelo.rows[0][3], "Procesamiento"]]
    assert modelo.rows[0][1].startswith("OP-")                  # código del lote
    assert not any(is_uuidv7(c) for fila in modelo.rows for c in fila)


def test_the_inspector_releases_from_the_screen(planta):
    presentador = _presentador(planta, planta.p.inspector,
                               {QualityPermissions.INSPECTION_DECIDE})
    inspeccion = presentador.pending().row_ids[0]
    ok, mensaje = presentador.decide(inspeccion, "RELEASED")
    assert ok, mensaje
    assert planta.estados_en_inventario(planta.filete) == {"AVAILABLE": "8"}
    assert planta.salida(planta.filete).quality_status is OutputQualityStatus.RELEASED
    assert presentador.pending().rows == []


def test_who_produced_cannot_decide_from_the_screen(planta):
    presentador = _presentador(planta, planta.p.operario,
                               {QualityPermissions.INSPECTION_DECIDE})
    ok, mensaje = presentador.decide(presentador.pending().row_ids[0], "RELEASED")
    assert not ok and "produjo" in mensaje
    assert planta.estados_en_inventario(planta.filete) == {"QUARANTINED": "8"}


def test_without_the_quality_permission_nothing_happens(planta):
    presentador = _presentador(planta, planta.p.gerente, set())
    ok, _ = presentador.decide(presentador.pending().row_ids[0], "RELEASED")
    assert not ok
    assert planta.lote_de(planta.filete) == "QUARANTINED"


def test_the_page_asks_for_a_reason_before_blocking(app, planta, monkeypatch):
    from frontend.desktop.modules.meat_processing.pages import quality_inspection_page as pag

    presentador = _presentador(planta, planta.p.inspector,
                               {QualityPermissions.INSPECTION_DECIDE})
    pagina = pag.PendingInspectionsPage(presentador)
    pagina.ensure_loaded()
    pagina.table.selectRow(0)
    monkeypatch.setattr(pag.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Temperatura fuera de rango", True)))
    avisos = []
    monkeypatch.setattr(pag.QMessageBox, "information", lambda *a: avisos.append(a[2]))
    monkeypatch.setattr(pag.QMessageBox, "warning", lambda *a: avisos.append(a[2]))
    pagina._on_decide("BLOCKED")
    assert "Bloquear" in avisos[0]
    assert "AVAILABLE" not in planta.estados_en_inventario(planta.filete)
    assert pagina.table.rowCount() == 0


def test_the_route_opens_the_quality_page(app, planta):
    from backend.infrastructure.desktop.meat_processing_factory import (
        create_meat_processing_view,
    )
    from frontend.desktop.modules.meat_processing.pages.quality_inspection_page import (
        QualityPage,
    )

    class _S(_Sesion):
        sucursal_id = None
        active_warehouse_id = ""
        permisos = frozenset()

    sesion = _S(planta.p.inspector, planta.p.branch, set())
    pagina = create_meat_processing_view(planta.conn, sesion)._page_builder("mp_quality")
    assert isinstance(pagina, QualityPage)
