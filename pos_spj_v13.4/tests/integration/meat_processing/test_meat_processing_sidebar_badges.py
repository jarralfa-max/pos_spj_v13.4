"""Procesamiento Cárnico: los contadores del sidebar llegan a la vista.

El sidebar declaraba seis claves de badge y el factory armaba la vista con
`badges={}`: ningún contador se veía. Aquí se construye la vista por el factory
real, con una sesión y datos sembrados por el dominio, y se lee el texto del
sidebar.
"""
from __future__ import annotations

import pytest

from backend.application.meat_processing.permissions import MeatProcessingPermissions as P
from backend.domain.meat_processing.entities import ProcessIncident
from backend.domain.meat_processing.enums import IncidentType
from backend.infrastructure.desktop.meat_processing_factory import create_meat_processing_view
from backend.shared.ids import new_uuid
from tests.integration.meat_processing.test_meat_processing_records import (  # noqa: F401
    SUCURSAL,
    USUARIO,
    Siembra,
    conn,
)


class _Sesion:
    is_active = True

    def __init__(self, permisos, *, branch_id=SUCURSAL):
        self.user_id = USUARIO
        self.active_branch_id = branch_id
        self.sucursal_id = branch_id
        self.active_warehouse_id = new_uuid()
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def _textos(vista):
    return [vista.sidebar.item(fila).text() for fila in range(vista.sidebar.count())]


def _incidencia_abierta(conn):
    siembra = Siembra(conn, SUCURSAL)
    orden = siembra.orden()
    siembra.guardar("incidents", ProcessIncident(
        id=new_uuid(), operation_id=new_uuid(), processing_order_id=orden.id,
        incident_type=IncidentType.EQUIPMENT_FAILURE, reported_by_user_id=USUARIO,
        description="sierra detenida"))


def test_the_sidebar_shows_the_open_incidents_count(app, conn):
    _incidencia_abierta(conn)

    vista = create_meat_processing_view(conn, _Sesion({P.INCIDENTS_VIEW, P.YIELD_VIEW}))

    assert _textos(vista) == ["Rendimientos (0)", "Incidencias (1)"]


def test_without_an_active_branch_there_are_no_counts(app, conn):
    _incidencia_abierta(conn)

    vista = create_meat_processing_view(conn, _Sesion({P.INCIDENTS_VIEW}, branch_id=""))

    assert _textos(vista) == ["Incidencias"]
