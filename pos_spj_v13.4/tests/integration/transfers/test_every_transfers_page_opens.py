"""Las 15 rutas de Transferencias se abren contra una base real, por el camino vivo.

Tercer módulo con el recorrido completo, tras Configuración y Mermas.

QUÉ CAMBIA AQUÍ
----------------
Las páginas NO tragan la excepción: `TransferWorkspacePage.reload` llama al
presenter sin `try/except`, así que un fallo se propaga y revienta la
navegación —igual que Configuración, al revés que Mermas—. Aun así se capturan
los modales, que cuestan nada y cubren las dos páginas que sí los usan.

Y el recorrido no es sólo "abre": las 15 rutas comparten UNA consulta
(`TransferWorkspaceQueryRepository.page`) que filtra por estado según un mapa
de 8 entradas. Las 7 restantes no filtran nada. Así que aquí interesa tanto que
la página abra como QUÉ acaba enseñando, y eso sólo se ve con datos sembrados
en estados distintos.
"""
from __future__ import annotations

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.application.transfers.permissions import TransferPermissions
from backend.infrastructure.desktop.transfers_factory import create_transfers_view
from backend.shared.ids import new_uuid
from frontend.desktop.modules.transfers.navigation.transfers_sidebar import TRANSFERS_NAV

PAGE_IDS = [entry.page_id for entry in TRANSFERS_NAV]

TODOS_LOS_PERMISOS = frozenset(
    valor for nombre, valor in vars(TransferPermissions).items()
    if not nombre.startswith("_") and isinstance(valor, str)
)

#: Un estado por cada valor que el mapa de filtros nombra, mas CANCELLED, que
#: no lo nombra ninguno: sin el, "no filtra" y "filtra y resulta que los coge
#: todos" darian el mismo resultado y no se distinguirian.
ESTADOS = (
    "DRAFT", "PENDING_APPROVAL", "RESERVED", "PICKING", "PARTIALLY_PICKED",
    "PICKED", "READY_TO_DISPATCH", "PARTIALLY_DISPATCHED", "IN_TRANSIT",
    "PARTIALLY_RECEIVED", "RECEIVED", "WITH_DIFFERENCES", "PENDING_RESOLUTION",
    "RETURN_IN_PROGRESS", "CANCELLED",
)


class _Sesion:
    """Mismo subconjunto que `SessionContext`/`LegacySessionAdapter`: API en
    español. Con todos los permisos, para poder abrir las 15."""

    user_id = "u1"
    is_active = True
    active_branch_id = "b1"
    sucursal_id = "b1"
    active_warehouse_id = "wh-9"

    def __init__(self, permisos=TODOS_LOS_PERMISOS) -> None:
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    base.up(c)
    c.commit()
    migrator.up(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def sembrado(conn):
    """Una transferencia por estado, con folio legible para poder afirmar sobre
    lo que acaba en la tabla."""
    for i, estado in enumerate(ESTADOS):
        conn.execute(
            "INSERT INTO stock_transfers (id, transfer_number, transfer_type,"
            " source_channel, source_module, origin_node_type,"
            " destination_node_type, requested_by_user_id, priority, status,"
            " operation_id, created_at, updated_at)"
            " VALUES (?,?,'INTERNAL','DESKTOP','TRANSFERS','BRANCH','BRANCH',"
            "'u1','NORMAL',?,?,?,?)",
            (new_uuid(), f"TR-{i:03d}", estado, new_uuid(),
             f"2026-09-{(i % 28) + 1:02d}T10:00:00+00:00",
             f"2026-09-{(i % 28) + 1:02d}T10:00:00+00:00"))
    conn.commit()


@pytest.fixture
def dialogos(monkeypatch):
    """Captura los modales en vez de dejar que bloqueen la suite."""
    capturados = []

    def _registrar(nivel):
        def _fn(_parent, titulo, texto, *a, **kw):
            capturados.append((nivel, titulo, texto))
            return QMessageBox.Ok
        return _fn

    for nivel in ("warning", "critical", "information", "question"):
        monkeypatch.setattr(QMessageBox, nivel, staticmethod(_registrar(nivel)))
    return capturados


def _vista(conn):
    return create_transfers_view(conn, _Sesion())


def _abrir_desde_cero(vista, page_id):
    """`TransfersView.__init__` ya abrio la primera entrada del sidebar y
    `show_route` cachea en `_pages`: sin evacuar, el caso de la ruta inicial no
    construye ni consulta nada y pasa siempre. Ese hueco ya se colo una vez en
    el recorrido de Mermas, y se vio porque la mutacion tumbaba una ruta pero
    no la otra que construye la misma pagina."""
    vista._pages.pop(page_id, None)
    vista.show_route(page_id)


def _folios(vista):
    tabla = vista.stack.currentWidget().table
    return {tabla.item(fila, 0).text() for fila in range(tabla.rowCount())}


# -- el recorrido -----------------------------------------------------------
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_on_an_empty_install(app, conn, dialogos, page_id):
    """Sin ninguna transferencia: una instalacion nueva no puede depender de
    que ya existan datos para que el modulo abra."""
    vista = _vista(conn)
    dialogos.clear()

    _abrir_desde_cero(vista, page_id)

    errores = [d for d in dialogos if d[0] in ("warning", "critical")]
    assert not errores, f"{page_id} aviso de un fallo al abrirse: {errores}"
    assert vista.stack.currentWidget().table.rowCount() == 0


@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_with_data(app, conn, sembrado, dialogos, page_id):
    """Con una transferencia en cada estado.

    Abrir con la tabla vacia es un camino distinto de mapear filas: el fallo de
    Configuracion vivia en el segundo, y el primero pasaba.
    """
    vista = _vista(conn)
    dialogos.clear()

    _abrir_desde_cero(vista, page_id)

    errores = [d for d in dialogos if d[0] in ("warning", "critical")]
    assert not errores, f"{page_id} aviso de un fallo con datos: {errores}"


def test_the_initial_route_opens_clean(app, conn, sembrado, dialogos):
    """El modulo carga una pagina antes de que nadie navegue."""
    vista = _vista(conn)

    errores = [d for d in dialogos if d[0] in ("warning", "critical")]
    assert not errores, f"la ruta inicial aviso de un fallo: {errores}"
    assert vista.stack.currentWidget() is not None


# -- el filtrado, que es lo que distingue una bandeja de otra ---------------
FILTRADAS = {
    "transfers_requests": ("DRAFT", "PENDING_APPROVAL"),
    "transfers_approvals": ("PENDING_APPROVAL",),
    "transfers_picking": ("RESERVED", "PICKING", "PARTIALLY_PICKED"),
    "transfers_ready_to_dispatch": ("PICKED", "READY_TO_DISPATCH"),
    "transfers_in_transit": ("PARTIALLY_DISPATCHED", "IN_TRANSIT"),
    "transfers_receipts": ("IN_TRANSIT", "PARTIALLY_RECEIVED", "RECEIVED"),
    "transfers_differences": ("WITH_DIFFERENCES", "PENDING_RESOLUTION"),
    "transfers_returns": ("RETURN_IN_PROGRESS",),
}


@pytest.mark.parametrize("page_id,estados", sorted(FILTRADAS.items()))
def test_the_worklist_shows_only_its_own_states(app, conn, sembrado, dialogos,
                                                page_id, estados):
    """Cada bandeja ensena su etapa y ninguna otra.

    Es la afirmacion que hace util a la pantalla: "Aprobaciones" que enseñe
    algo ya despachado lleva a aprobar lo que ya salio.
    """
    vista = _vista(conn)
    _abrir_desde_cero(vista, page_id)

    assert _folios(vista) == {f"TR-{ESTADOS.index(e):03d}" for e in estados}


# -- lo que el recorrido encontro, medido y fijado --------------------------
#: Rutas cuyo `page_id` NO esta en el mapa de filtros del repositorio, de modo
#: que la consulta devuelve TODAS las transferencias, y cuya pagina es la lista
#: generica sin nada propio: misma clase, mismas 5 columnas, mismo contenido,
#: distinto titulo.
#:
#: `transfers_overview` y `transfers_analytics` tampoco filtran, pero SI tienen
#: pagina propia (KPIs y grafica), asi que no estan aqui.
#:
#: Medido hoy. Solo puede ENCOGER.
SIN_CONTENIDO_PROPIO = {
    "transfers_suggestions", "transfers_traceability", "transfers_alerts",
    "transfers_audit", "transfers_settings",
}


@pytest.mark.parametrize("page_id", sorted(SIN_CONTENIDO_PROPIO))
def test_these_routes_still_show_the_undifferentiated_list(app, conn, sembrado,
                                                           dialogos, page_id):
    """Estas 5 ensenan la lista completa de transferencias, sin filtrar.

    "Configuracion" enseñando transferencias, o "Auditoria —registro inmutable
    de acciones— " enseñando transferencias en vez de acciones, no es una
    pantalla a medias: es otra pantalla. Se fija aqui para que se vea en la
    suite en vez de contarse como ruta terminada, no para bendecirlo.
    """
    vista = _vista(conn)
    _abrir_desde_cero(vista, page_id)

    assert _folios(vista) == {f"TR-{i:03d}" for i in range(len(ESTADOS))}


def test_no_route_left_the_undifferentiated_set_without_updating_it(
        app, conn, sembrado, dialogos):
    """Si una de las 5 recibe su consulta propia, esto obliga a bajarla del
    conjunto en vez de dejar el trinquete mintiendo."""
    todas = {f"TR-{i:03d}" for i in range(len(ESTADOS))}
    sin_filtrar = set()
    for page_id in PAGE_IDS:
        vista = _vista(conn)
        _abrir_desde_cero(vista, page_id)
        if _folios(vista) == todas:
            sin_filtrar.add(page_id)

    # Estas dos tampoco filtran, pero tienen pagina propia.
    sin_filtrar -= {"transfers_overview", "transfers_analytics"}

    resueltas = sorted(SIN_CONTENIDO_PROPIO - sin_filtrar)
    assert not resueltas, (
        "Ya no ensenan la lista sin filtrar; quitalas de SIN_CONTENIDO_PROPIO "
        f"para que el trinquete baje: {resueltas}")
    nuevas = sorted(sin_filtrar - SIN_CONTENIDO_PROPIO)
    assert not nuevas, f"Rutas nuevas sin consulta propia: {nuevas}"


def test_the_sidebar_shows_every_route_to_a_fully_permitted_user(app, conn, dialogos):
    """Una ruta que el sidebar nunca muestra es inalcanzable aunque su pagina
    funcione."""
    vista = _vista(conn)
    mostradas = {
        vista.sidebar.item(fila).data(0x0100)  # Qt.UserRole
        for fila in range(vista.sidebar.count())
    }
    assert mostradas == set(PAGE_IDS)
