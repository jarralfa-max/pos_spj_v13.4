"""Las 17 rutas de Inteligencia de Negocios se abren contra una base real.

Quinto módulo con el recorrido completo, tras Configuración, Mermas,
Transferencias y Procesamiento Cárnico.

ESTE MÓDULO YA TENÍA 26 PRUEBAS. ESTO NO LAS REPITE
-----------------------------------------------------
Medido antes de escribir nada, porque el módulo parecía el mejor cubierto de
los cinco y había que comprobar si el recorrido aportaba algo:

  - NINGUNA prueba de BI migra una base real. La que recorre las rutas
    (`tests/unit/business_intelligence/test_business_intelligence_routes.py`)
    usa `sqlite3.connect(":memory:")` a secas: una base SIN UNA SOLA TABLA.
    Que una página se construya contra eso no dice nada sobre si funciona.

  - Construir no es cargar. `build_page()` sólo instancia; los datos se piden
    en `ensure_loaded()`, y a ése sólo lo llama `show_route()`. Dos de los
    archivos existentes lo dicen en su propio docstring: "does NOT call
    `page.ensure_loaded()`/`refresh()` on a real page". Entre esos dos están
    el tablero ejecutivo y la sección analítica —que es la clase detrás de 10
    de las 17 rutas—.

O sea: 16 rutas reales, y hasta aquí ninguna se había abierto nunca contra un
esquema de verdad. Esto entra por `show_route`, que es el camino del shell.

POR QUÉ LOS DIÁLOGOS SON LA AFIRMACIÓN
----------------------------------------
Las 6 familias de página tragan la excepción en un `QMessageBox` (§"surface,
never crash the page"). Igual que en Mermas, un recorrido que sólo comprobara
"no revienta" sería verde vacío: toda página abre aunque su consulta falle.

Se distingue el nivel a propósito: `warning`/`critical` son fallos, pero tres
páginas usan `information` para un "todavía no hay datos" legítimo
(`ForecastUnavailableError`, `ScenarioUnavailableError`,
`RecommendationUnavailableError`). Exigir cero `information` haría fallar el
estado vacío honesto, que es justo lo que se espera en una base recién
migrada.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.application.analytics.permissions import AnalyticsPermissions
from backend.shared.ids import new_uuid
from frontend.desktop.modules.business_intelligence.business_intelligence_routes import (
    _REAL_ROUTE_BUILDERS,
)
from frontend.desktop.modules.business_intelligence.business_intelligence_view import (
    BusinessIntelligenceView,
)
from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
    BUSINESS_INTELLIGENCE_NAV,
)
from frontend.desktop.modules.business_intelligence.pages import (
    BusinessIntelligencePlaceholderPage,
)
from frontend.desktop.shell.modules.session_access import sidebar_permission_checker

PAGE_IDS = [entry.page_id for entry in BUSINESS_INTELLIGENCE_NAV]

#: Rutas con pagina real, leidas del registro del propio modulo en vez de
#: copiadas: si alguien cablea una nueva, el recorrido la cubre sin tocar esto.
RUTAS_REALES = set(_REAL_ROUTE_BUILDERS)

TODOS_LOS_PERMISOS = frozenset(
    valor for nombre, valor in vars(AnalyticsPermissions).items()
    if not nombre.startswith("_") and isinstance(valor, str)
)

#: HALLAZGO DE ESTE RECORRIDO, no una excepcion de conveniencia.
#:
#: `bi_cash` consulta `movimientos_caja` y `cierres_caja`, que NO EXISTEN en una
#: base migrada entera. El contexto de Caja se reconstruyo con nombres
#: canonicos en ingles —`cash_ledger_entries`, `cash_cuts`, `cash_counts`,
#: `cash_shifts`...— y el servicio de consulta de BI se quedo apuntando a los
#: nombres legacy en español.
#:
#: Como `BiCashQueryService._q` traga el error y devuelve `[]`, la seccion
#: "Caja" del tablero pinta CEROS. No hay aviso, no hay hueco visible: se lee
#: como un negocio que no movio efectivo.
#:
#: El alcance esta medido: SOLO `bi_cash_query_service.py` lee esos nombres, en
#: 5 consultas, todas muertas. Los candidatos canonicos existen y tienen las
#: columnas necesarias —`cash_ledger_entries` (amount/direction/movement_type/
#: branch_id) para los movimientos y `cash_cuts` (expected_cash/counted_cash/
#: difference/cut_type) para los cortes—, pero el mapeo no es un renombrado:
#: `direction` sustituye al signo del importe y `cash_cuts` distingue tipos de
#: corte donde `cierres_caja` tenia apertura/cierre. Elegirlo es una decision
#: de dominio, asi que se deja fijado para que se VEA, y la prueba de abajo
#: obliga a quitarlo de aqui en cuanto se arregle.
SECCIONES_ROTAS = {"bi_cash"}

#: Las tablas que `bi_cash` busca y que ninguna migracion crea.
TABLAS_INEXISTENTES = ("movimientos_caja", "cierres_caja")


class _Sesion:
    """Mismo subconjunto que `SessionContext`/`LegacySessionAdapter`: API en
    español. Identidades UUIDv7, que es lo que el dominio exige."""

    is_active = True

    def __init__(self, permisos=TODOS_LOS_PERMISOS) -> None:
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.sucursal_id = self.active_branch_id
        self.active_warehouse_id = new_uuid()
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    """Base migrada entera. Es la diferencia con las 26 pruebas que ya existen,
    que construyen contra una base vacia sin tablas."""
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
def sesion():
    return _Sesion()


@pytest.fixture
def dialogos(monkeypatch):
    """Captura los modales en vez de dejar que bloqueen.

    Es tambien la comprobacion de verdad: estas paginas convierten un fallo de
    carga en un aviso, asi que un `warning` ES el fallo.
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


@pytest.fixture
def tragados(caplog):
    """Vigila `spj.bi`, donde cuatro servicios de consulta tragan el SQL roto.

    ESTO LO ANADIO UNA MUTACION QUE NO SE CAZO. La primera version de este
    archivo afirmaba solo sobre los dialogos y daba 54 verdes con la consulta
    de ventas del tablero apuntando a una tabla inexistente.

    El motivo es una TERCERA capa que traga, mas profunda que la pagina:

        def _q(self, sql, params=()):
            try:
                return self._conn.execute(sql, params).fetchall()
            except Exception as e:
                logger.warning("BiSalesQueryService: %s", e)
                return []

    Lo hacen igual `bi_sales`, `bi_cash`, `bi_finance` y `bi_inventory`. Asi
    que una consulta rota no llega nunca al `except` de la pagina: el tablero
    pinta CEROS, que en un tablero ejecutivo se lee como "no se vendio nada".
    Peor que el caso de Procesamiento Carnico, donde al menos la tabla vacia
    era ambigua; aqui el cero parece un dato.

    El log es la unica señal que queda, y por eso se afirma sobre el.
    """
    caplog.set_level(logging.WARNING, logger="spj.bi")
    return caplog


@pytest.fixture
def vistas(app):
    """Construye vistas y las DESTRUYE al terminar cada prueba.

    Sin esto cada caso dejaba viva una vista completa de BI con sus paginas y
    sus widgets. En aislamiento no se nota; junto al resto de la suite Qt de
    este repositorio, si: la primera version de este archivo hizo que
    `tests/integration/business_intelligence/` + `tests/unit/
    business_intelligence/` en un mismo proceso tardara 4h13m en vez de ~6min,
    y terminara con un RuntimeError de objeto C++ ya borrado en
    `virtual_keyboard.py`. No era un fallo de la prueba unitaria: era el peso
    acumulado de las vistas que estas dejaban sin soltar.
    """
    creadas = []

    def _crear(conn, sesion):
        """Compuesta igual que `BusinessIntelligenceModuleActivator._build_view`:
        la vista arma su propio `page_builder` a partir de la conexion."""
        vista = BusinessIntelligenceView(
            has_permission=sidebar_permission_checker(sesion),
            connection=conn,
            branch_id=sesion.active_branch_id,
            actor_user_id=sesion.user_id,
        )
        creadas.append(vista)
        return vista

    yield _crear

    for vista in creadas:
        vista.setParent(None)
        vista.deleteLater()
    creadas.clear()
    app.processEvents()


def _abrir_desde_cero(vista, page_id):
    """`show_route` cachea en `_pages` y la vista ya abrio la primera entrada
    del sidebar: sin evacuar, el caso de la ruta inicial no carga nada y pasa
    siempre. Ese hueco ya se colo una vez en el recorrido de Mermas."""
    vista._pages.pop(page_id, None)
    vista.show_route(page_id)


def _errores(dialogos):
    """`information` queda fuera a proposito: tres paginas lo usan para decir
    "todavia no hay datos", que es el estado correcto en una base recien
    migrada. Ver el docstring del modulo."""
    return [d for d in dialogos if d[0] in ("warning", "critical")]


# -- el recorrido -----------------------------------------------------------
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_against_a_migrated_database(app, vistas, conn, sesion,
                                                     dialogos, tragados, page_id):
    """Instalacion recien migrada, sin ningun movimiento registrado.

    Un tablero sin datos es un estado legitimo —el negocio acaba de empezar—,
    asi que abrir no puede depender de que ya haya ventas que agregar.
    """
    vista = vistas(conn, sesion)
    # Se limpian LOS DOS: construir la vista ya abrio la primera entrada del
    # sidebar, y sin vaciar el log sus avisos se atribuyen a todas las rutas.
    dialogos.clear()
    tragados.clear()

    _abrir_desde_cero(vista, page_id)

    assert vista.active_route == page_id
    assert not _errores(dialogos), (
        f"{page_id} aviso de un fallo al abrirse: {_errores(dialogos)}")
    if page_id not in SECCIONES_ROTAS:
        assert not tragados.records, (
            f"{page_id} trago un fallo de consulta y pinto ceros: "
            f"{[r.getMessage() for r in tragados.records]}")


def test_the_initial_route_opens_clean(app, vistas, conn, sesion, dialogos):
    """La vista abre la primera entrada visible del sidebar al construirse, asi
    que el modulo carga una pagina antes de que nadie navegue."""
    vista = vistas(conn, sesion)

    assert vista.active_route is not None
    assert not _errores(dialogos), (
        f"la ruta inicial aviso de un fallo: {_errores(dialogos)}")


@pytest.mark.parametrize("page_id", sorted(RUTAS_REALES))
def test_the_real_route_reaches_its_presenter_without_swallowing(
        app, vistas, conn, sesion, dialogos, page_id):
    """Las 16 rutas reales, abiertas dos veces.

    La segunda apertura pasa por la rama cacheada de `show_route` y por el
    `_loaded` de la pagina: es donde vive un fallo que la primera no toca, como
    un `invalidate()` que recalcula sobre estado ya construido.
    """
    vista = vistas(conn, sesion)
    _abrir_desde_cero(vista, page_id)
    dialogos.clear()

    vista.show_route(page_id)          # segunda vez, ya cacheada

    assert not _errores(dialogos), (
        f"{page_id} fallo al reabrirse: {_errores(dialogos)}")


# -- el hallazgo, fijado para que se vea -----------------------------------
def test_the_cash_section_still_queries_tables_that_do_not_exist(
        app, vistas, conn, sesion, dialogos, tragados):
    """La seccion "Caja" del tablero pinta ceros contra una base migrada.

    Esto NO bendice el fallo: lo hace visible. Mientras siga roto, esta prueba
    pasa y describe el problema; en cuanto se arregle, falla y obliga a sacar
    `bi_cash` de `SECCIONES_ROTAS`, de modo que el trinquete no pueda quedarse
    mintiendo.
    """
    existentes = {
        fila[0] for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }
    faltan = [t for t in TABLAS_INEXISTENTES if t not in existentes]
    assert faltan == list(TABLAS_INEXISTENTES), (
        "Alguna de las tablas que busca bi_cash ya existe; revisa si la "
        f"seccion quedo arreglada y actualiza SECCIONES_ROTAS. Faltan: {faltan}")

    vista = vistas(conn, sesion)
    _abrir_desde_cero(vista, "bi_cash")

    mensajes = [r.getMessage() for r in tragados.records]
    assert any("no such table" in m for m in mensajes), (
        "bi_cash ya no traga un fallo de tabla inexistente; quitalo de "
        f"SECCIONES_ROTAS para que el trinquete baje. Log: {mensajes}")


def test_no_other_section_is_silently_broken(app, vistas, conn, sesion, dialogos,
                                             tragados):
    """El conjunto de secciones rotas solo puede encoger.

    Recorre las 16 reales y recoge cuales tragan; si aparece una nueva, la
    nombra en vez de dejar que se sume al silencio de fondo.
    """
    rotas = set()
    for page_id in sorted(RUTAS_REALES):
        vista = vistas(conn, sesion)
        tragados.clear()
        _abrir_desde_cero(vista, page_id)
        if any("no such table" in r.getMessage() for r in tragados.records):
            rotas.add(page_id)

    nuevas = sorted(rotas - SECCIONES_ROTAS)
    assert not nuevas, f"Secciones que empezaron a tragar consultas rotas: {nuevas}"
    arregladas = sorted(SECCIONES_ROTAS - rotas)
    assert not arregladas, (
        f"Ya no estan rotas; quitalas de SECCIONES_ROTAS: {arregladas}")


# -- real vs placeholder, medido ruta a ruta --------------------------------
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_is_the_kind_of_page_we_think_it_is(app, vistas, conn, sesion,
                                                      dialogos, page_id):
    """16 rutas reales y una placeholder (`bi_production`).

    Se mide abriendo, no leyendo el registro: `build_page` sólo devuelve la
    pagina real cuando recibe una conexion, asi que el registro por si solo no
    prueba que la ruta viva llegue a construirla.
    """
    vista = vistas(conn, sesion)
    _abrir_desde_cero(vista, page_id)
    pagina = vista.stack.currentWidget()

    es_placeholder = isinstance(pagina, BusinessIntelligencePlaceholderPage)
    if page_id in RUTAS_REALES:
        assert not es_placeholder, (
            f"{page_id} deberia tener pagina real y cayo al placeholder")
    else:
        assert es_placeholder, (
            f"{page_id} ya tiene pagina real ({type(pagina).__name__}); "
            "registrala en _REAL_ROUTE_BUILDERS para que el trinquete suba")


def test_production_is_the_only_route_still_without_a_page(app, vistas, conn, sesion,
                                                           dialogos):
    """`bi_production` sigue vacia por un motivo concreto y documentado: la
    fachada `BiDashboardQueryService` no expone ninguna fuente de produccion.

    Se fija para que el dia que se conecte haya que actualizarlo aqui, en vez
    de que el hueco se cierre sin que nadie lo note —o peor, que otra ruta
    caiga al placeholder y se confunda con esta.
    """
    sin_pagina = set(PAGE_IDS) - RUTAS_REALES
    assert sin_pagina == {"bi_production"}, (
        f"Cambio el conjunto de rutas sin pagina real: {sorted(sin_pagina)}")


# -- el sidebar -------------------------------------------------------------
def test_the_sidebar_shows_every_route_to_a_fully_permitted_user(
        app, vistas, conn, sesion, dialogos):
    """Regresion del sidebar vacio: el activator sondeaba `has_permission`/
    `permissions`, atributos que ninguna de las dos sesiones vivas define, asi
    que las rutas reales quedaban inalcanzables tras un sidebar sin entradas."""
    vista = vistas(conn, sesion)
    mostradas = {
        vista.sidebar.item(fila).data(0x0100)  # Qt.UserRole
        for fila in range(vista.sidebar.count())
    }
    assert mostradas == set(PAGE_IDS)


def test_a_user_without_permissions_reaches_nothing(app, vistas, conn, dialogos):
    """Fail-closed (§23): sin permisos no hay entradas, y sin sesion tampoco."""
    assert vistas(conn, _Sesion(permisos=frozenset())).sidebar.count() == 0

    # Esta no pasa por `vistas` porque la fabrica lee atributos de la sesion y
    # aqui el caso es NO tener ninguna; se suelta a mano por el mismo motivo.
    sin_sesion = BusinessIntelligenceView(
        has_permission=sidebar_permission_checker(None), connection=conn)
    try:
        assert sin_sesion.sidebar.count() == 0
    finally:
        sin_sesion.setParent(None)
        sin_sesion.deleteLater()
        app.processEvents()
