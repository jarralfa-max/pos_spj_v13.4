"""Las 16 rutas de Mermas se abren contra una base real, por el camino vivo.

POR QUÉ ESTE ARCHIVO EXISTE
----------------------------
Mismo recorrido que `tests/integration/configuracion/
test_every_configuracion_page_opens.py`, tras encontrar allí dos fallos
seguidos del mismo tipo: código que se lee bien y ninguna prueba que lo
ejecute contra la base real.

DOS DIFERENCIAS QUE CAMBIAN LA PRUEBA
--------------------------------------
1) El camino vivo NO es `losses_routes.build_page`, que devuelve placeholder
   para las 16 rutas. Es `losses_factory.create_losses_view`, cuyo
   `page_builder` construye 5 páginas REALES. Medir sobre `build_page` diría
   que todo es placeholder y no probaría nada.

2) Estas páginas NO propagan la excepción: la tragan en un `QMessageBox`
   (`analytics_page.py:16`, `yield_monitoring_page.py:85`). Así que un
   recorrido que sólo comprobara "no revienta" sería VERDE VACÍO: cada página
   "abre" aunque su consulta falle entera. Por eso se capturan los diálogos y
   la afirmación de verdad es que no hubo ninguno.

Se entra por `view.show_route(page_id)`, que es la ruta exacta por la que
reventó Configuración: `show_route` -> `ensure_loaded()`.

LO QUE ESTE RECORRIDO **NO** CUBRE
-----------------------------------
Comprobado con mutación, una por página: romper una tabla en el repositorio de
analítica hace fallar `losses_overview` y `losses_analysis`; en el de
rendimientos, `losses_yields`; en el de registro, `losses_registration`. Cada
una cae en su ruta y en ninguna otra.

`losses_investigations` es la excepción: `RootCausePage` NO tiene
`ensure_loaded` y sus `SearchSelector` sólo consultan cuando alguien escribe,
así que al abrirse no toca la base. Aquí se comprueba que se construye, y nada
más. Un fallo en sus consultas sólo aparecería al teclear, y eso necesita otra
prueba —no la finge ésta.

Las 11 rutas placeholder tampoco consultan nada; su caso vale por lo que
afirma abajo: que siguen siendo placeholder y no otra cosa.
"""
from __future__ import annotations

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.application.losses.permissions import LossPermissions
from backend.infrastructure.desktop.losses_factory import create_losses_view
from frontend.desktop.modules.losses.navigation.losses_sidebar import LOSSES_NAV
from frontend.desktop.modules.losses.pages import LossesPlaceholderPage

PAGE_IDS = [entry.page_id for entry in LOSSES_NAV]

#: Las 5 rutas que el composition root construye de verdad; el resto siguen
#: siendo placeholder declarado. La lista se afirma abajo en vez de asumirse:
#: si una deja de ser real, esto lo dice en vez de pasar en silencio.
RUTAS_REALES = {
    "losses_overview", "losses_registration", "losses_investigations",
    "losses_yields", "losses_analysis",
}

TODOS_LOS_PERMISOS = frozenset(
    valor for nombre, valor in vars(LossPermissions).items()
    if not nombre.startswith("_") and isinstance(valor, str)
)


class _Sesion:
    """Mismo subconjunto que `SessionContext` y `LegacySessionAdapter`: API en
    español, `active_warehouse_id`. Con TODOS los permisos, a propósito: el
    objetivo es abrir las 16, no comprobar el filtrado del sidebar."""

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
    """Base migrada ENTERA, no sólo la migración 174 de Mermas.

    El módulo lee inventario, productos y sucursales; migrar sólo lo suyo
    dejaría fuera justo las tablas cuyos nombres podrían no cuadrar.
    """
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
def dialogos(monkeypatch):
    """Captura los modales en vez de dejar que bloqueen.

    Además de desbloquear la prueba, es la comprobación de verdad: estas
    páginas convierten un fallo de carga en un aviso, así que un diálogo ES
    el fallo. `QMessageBox` es la misma clase en todos los módulos, así que
    parchear los estáticos aquí los cubre todos.
    """
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
    return create_losses_view(conn, _Sesion())


def _abrir_desde_cero(vista, page_id):
    """Abre la ruta forzando que la pagina se CONSTRUYA y se cargue.

    `LossesView.__init__` ya abrio la primera entrada visible del sidebar, y
    `show_route` cachea en `_pages`: pedir esa misma ruta despues no construye
    nada ni vuelve a consultar. Sin esto, el caso parametrizado de la ruta
    inicial pasaba SIEMPRE —comprobado rompiendo el repositorio de analitica:
    fallaban `losses_analysis` y la ruta inicial, pero `losses_overview`, que
    construye exactamente la misma pagina, salia verde.
    """
    vista._pages.pop(page_id, None)
    vista.show_route(page_id)


# ── el recorrido ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_without_an_error_dialog(app, conn, dialogos, page_id):
    """Instalación recién migrada, sin ningún expediente cargado.

    Una pantalla de mermas vacía es un estado legítimo —nadie ha registrado
    pérdidas todavía—, así que abrir no puede depender de que haya datos.
    """
    vista = _vista(conn)
    dialogos.clear()          # descarta lo que emitiera la ruta inicial

    _abrir_desde_cero(vista, page_id)

    assert vista.active_route == page_id
    errores = [d for d in dialogos if d[0] in ("warning", "critical")]
    assert not errores, f"{page_id} avisó de un fallo al abrirse: {errores}"


def test_the_initial_route_opens_clean(app, conn, dialogos):
    """`LossesView.__init__` abre la primera entrada visible del sidebar, así
    que el módulo carga una página ANTES de que nadie navegue. Si esa revienta,
    el módulo entero se ve roto nada más entrar."""
    vista = _vista(conn)

    assert vista.active_route is not None
    errores = [d for d in dialogos if d[0] in ("warning", "critical")]
    assert not errores, f"la ruta inicial avisó de un fallo: {errores}"


# ── real vs placeholder, medido y no asumido ────────────────────────────────
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_is_the_kind_of_page_we_think_it_is(app, conn, dialogos, page_id):
    """El composition root construye 5 páginas reales y delega el resto en
    `build_page`, que las hace placeholder.

    Esto se mide en vez de asumirse por lo que pasó al medir este módulo la
    vez anterior: se juzgó sobre `build_page` y salió "las 16 son placeholder",
    incluidas las 4 que sí tenían página. Si una real se rompe y cae al
    placeholder, aquí se ve.
    """
    vista = _vista(conn)
    _abrir_desde_cero(vista, page_id)
    pagina = vista.stack.currentWidget()

    es_placeholder = isinstance(pagina, LossesPlaceholderPage)
    if page_id in RUTAS_REALES:
        assert not es_placeholder, (
            f"{page_id} deberia tener pagina real y cayo al placeholder")
    else:
        assert es_placeholder, (
            f"{page_id} ya tiene pagina real ({type(pagina).__name__}); "
            "anadela a RUTAS_REALES para que el trinquete suba")


def test_the_sidebar_shows_every_route_to_a_fully_permitted_user(app, conn, dialogos):
    """Una ruta que el sidebar nunca muestra es inalcanzable aunque su página
    funcione — el fallo de medición que ya ocurrió aquí, una capa más arriba."""
    vista = _vista(conn)
    mostradas = {
        vista.sidebar.item(fila).data(0x0100)  # Qt.UserRole
        for fila in range(vista.sidebar.count())
    }
    assert mostradas == set(PAGE_IDS)
