"""Las 29 rutas de Procesamiento Cárnico se abren contra una base real.

Cuarto módulo con el recorrido completo, tras Configuración, Mermas y
Transferencias.

POR QUÉ AQUÍ UN RECORRIDO INGENUO SERÍA DOBLEMENTE VACÍO
---------------------------------------------------------
En Mermas un fallo de carga acababa en un `QMessageBox`: feo, pero visible.
Aquí no hay ni eso. `ProcessingOrderPresenter.orders()` hace:

    except Exception:
        logger.exception("ProcessingOrderPresenter.orders failed")
        return TableViewModel()

O sea: cualquier fallo de la consulta se convierte en una TABLA VACÍA, que es
exactamente lo que se ve cuando la sucursal no tiene órdenes. No hay diálogo,
no hay excepción, no hay diferencia visible entre "no hay nada" y "está roto".

Así que "la página abre y no revienta" no demuestra nada en este módulo. Lo
único que separa un caso del otro es SEMBRAR órdenes y exigir que salgan. Eso
hace `test_the_orders_page_actually_shows_the_seeded_orders`, y es la prueba
que sostiene al resto del archivo.

Se vigila además el logger: es la única señal que el código emite cuando traga,
y sin mirarla el tragado es indistinguible del silencio legítimo.

UNA TRAMPA QUE ESTO FIJA DE PASO
---------------------------------
`ProcessingOrder` exige UUIDv7 en `branch_id`. Una sesión cuya sucursal sea un
identificador legacy no-UUID hace reventar la construcción de la entidad, lo
traga el mismo `except`, y la pantalla queda vacía sin decir nada. Por eso la
sesión de prueba usa UUIDv7 de verdad y hay un caso explícito para el no-UUID:
la pantalla vacía por ese motivo es un fallo, no un estado.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.domain.meat_processing.slaughter.feature_flag import SLAUGHTER_ENABLED
from backend.infrastructure.desktop.meat_processing_factory import (
    create_meat_processing_view,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (
    MEAT_PROCESSING_NAV,
)
from frontend.desktop.modules.meat_processing.pages import MeatProcessingPlaceholderPage

PAGE_IDS = [entry.page_id for entry in MEAT_PROCESSING_NAV]
RUTAS_TRAS_FLAG = {e.page_id for e in MEAT_PROCESSING_NAV if e.feature_flag}
RUTAS_SIEMPRE = [p for p in PAGE_IDS if p not in RUTAS_TRAS_FLAG]

#: La UNICA ruta con pagina real hoy; las otras 28 caen al placeholder de
#: `build_page`. Medido, no supuesto: lo comprueba
#: `test_the_route_is_the_kind_of_page_we_think_it_is` ruta por ruta.
#: Solo puede CRECER — y cuando crezca, esa prueba obliga a actualizarlo.
#: PASS 6 añadió los registros con tablas reales detrás (ver
#: `_RECORD_ROUTES` en `meat_processing_factory.py`) y Pesajes y consumos.
RUTAS_REALES = {
    "mp_processing_orders", "mp_preparation", "mp_active_processing",
    "mp_weighings_consumptions", "mp_cutting", "mp_derived_products",
    "mp_packaging_labeling", "mp_produced_lots", "mp_yields", "mp_quality",
    "mp_rework", "mp_incidents", "mp_audit",
}

TODOS_LOS_PERMISOS = frozenset(
    valor for nombre, valor in vars(MeatProcessingPermissions).items()
    if not nombre.startswith("_") and isinstance(valor, str)
)

#: Tipos validos segun el CHECK de `processing_orders`.
ORDENES_SEMBRADAS = (
    ("CUTTING", "DRAFT"),
    ("DEBONING", "APPROVED"),
    ("GRINDING", "RELEASED"),
)


class _Sesion:
    """Mismo subconjunto que `SessionContext`/`LegacySessionAdapter`: API en
    español, `active_branch_id`/`active_warehouse_id`.

    Las identidades son UUIDv7 de verdad porque el dominio las exige; ver el
    docstring del módulo.
    """

    is_active = True

    def __init__(self, *, branch_id=None, permisos=TODOS_LOS_PERMISOS) -> None:
        self.user_id = new_uuid()
        self.active_branch_id = branch_id if branch_id is not None else new_uuid()
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


def _sembrar(conn, branch_id):
    """Una orden por tipo/estado, en la sucursal de la sesion."""
    for i, (tipo, estado) in enumerate(ORDENES_SEMBRADAS):
        conn.execute(
            "INSERT INTO processing_orders (id, operation_id, branch_id,"
            " warehouse_id, process_type, target_product_id,"
            " created_by_user_id, created_at, updated_at, planned_quantity,"
            " planned_weight, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), new_uuid(), branch_id, new_uuid(), tipo, new_uuid(),
             new_uuid(), f"2026-09-0{i + 1}T10:00:00+00:00",
             f"2026-09-0{i + 1}T10:00:00+00:00", i + 1, f"1{i}.5", estado))
    conn.commit()


@pytest.fixture
def dialogos(monkeypatch):
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
    """El presenter convierte cualquier fallo en tabla vacia y sólo deja rastro
    en el log. Sin vigilarlo, un modulo entero roto se lee como un modulo
    vacio."""
    caplog.set_level(logging.ERROR, logger="spj.ui.meat_processing")
    return caplog


def _vista(conn, sesion):
    return create_meat_processing_view(conn, sesion)


def _abrir_desde_cero(vista, page_id):
    """`MeatProcessingView.__init__` ya abrio la primera entrada del sidebar y
    `show_route` cachea en `_pages`: sin evacuar, el caso de la ruta inicial no
    construye ni consulta nada y pasa siempre. Ese hueco ya se colo una vez en
    el recorrido de Mermas."""
    vista._pages.pop(page_id, None)
    vista.show_route(page_id)


def _errores(dialogos):
    return [d for d in dialogos if d[0] in ("warning", "critical")]


# -- el recorrido -----------------------------------------------------------
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_on_an_empty_install(app, conn, sesion, dialogos,
                                             tragados, page_id):
    """Instalacion recien migrada, sin ninguna orden.

    Se recorren las 29, incluidas las 10 que el feature flag oculta del
    sidebar: `show_route` las construye igual si algo las invoca, y una ruta
    que revienta al construirse no deja de ser un fallo por estar escondida.
    """
    vista = _vista(conn, sesion)
    dialogos.clear()
    tragados.clear()

    _abrir_desde_cero(vista, page_id)

    assert vista.active_route == page_id
    assert not _errores(dialogos), f"{page_id} aviso de un fallo: {_errores(dialogos)}"
    assert not tragados.records, (
        f"{page_id} trago un fallo en el log: "
        f"{[r.getMessage() for r in tragados.records]}")


@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_opens_with_data(app, conn, sesion, dialogos, tragados, page_id):
    """Con ordenes sembradas: mapear filas es un camino distinto de pintar una
    tabla vacia, y el fallo de Configuracion vivia justo en el segundo."""
    _sembrar(conn, sesion.active_branch_id)
    vista = _vista(conn, sesion)
    dialogos.clear()
    tragados.clear()

    _abrir_desde_cero(vista, page_id)

    assert not _errores(dialogos), f"{page_id} aviso de un fallo: {_errores(dialogos)}"
    assert not tragados.records, (
        f"{page_id} trago un fallo en el log: "
        f"{[r.getMessage() for r in tragados.records]}")


def test_the_initial_route_opens_clean(app, conn, sesion, dialogos, tragados):
    """El modulo carga una pagina antes de que nadie navegue."""
    _sembrar(conn, sesion.active_branch_id)

    vista = _vista(conn, sesion)

    assert vista.active_route is not None
    assert not _errores(dialogos)
    assert not tragados.records


# -- la prueba que sostiene a todas las demas -------------------------------
def test_the_orders_page_actually_shows_the_seeded_orders(app, conn, sesion,
                                                          dialogos, tragados):
    """La UNICA que distingue "funciona" de "se trago el fallo".

    Todo lo de arriba pasaria igual con la consulta rota, porque el presenter
    devuelve una tabla vacia en vez de propagar. Aqui se siembran tres ordenes
    y se exige que las tres salgan.
    """
    _sembrar(conn, sesion.active_branch_id)
    vista = _vista(conn, sesion)

    _abrir_desde_cero(vista, "mp_processing_orders")
    tabla = vista.stack.currentWidget()._table

    assert tabla.rowCount() == len(ORDENES_SEMBRADAS), (
        "La pagina de Ordenes no enseño las ordenes sembradas. Si el log de "
        f"spj.ui.meat_processing dice algo, ahi esta la causa: "
        f"{[r.getMessage() for r in tragados.records]}")
    assert not tragados.records


def test_orders_from_another_branch_are_not_shown(app, conn, dialogos, tragados):
    """El aislamiento por sucursal es la razon de que la consulta filtre.

    Sin esto, la afirmacion de arriba pasaria igual con un `SELECT *` sin
    `WHERE`, que enseñaria a cada sucursal las ordenes de todas.
    """
    sesion = _Sesion()
    _sembrar(conn, new_uuid())          # ordenes de OTRA sucursal
    vista = _vista(conn, sesion)

    _abrir_desde_cero(vista, "mp_processing_orders")

    assert vista.stack.currentWidget()._table.rowCount() == 0
    assert not tragados.records


def test_a_non_uuid_branch_is_not_silently_empty(app, conn, dialogos, tragados):
    """La trampa del docstring, fijada.

    `ProcessingOrder` exige UUIDv7 en `branch_id`. Con una sucursal legacy la
    entidad revienta, el `except` lo traga y la pantalla queda vacia sin decir
    nada — identico a "esta sucursal no tiene ordenes".

    Esta prueba NO bendice ese comportamiento: comprueba que, si ocurre, al
    menos queda registrado. Una pantalla vacia sin rastro seria indetectable.
    """
    sesion = _Sesion(branch_id="sucursal-legacy-1")
    _sembrar(conn, new_uuid())
    conn.execute("UPDATE processing_orders SET branch_id='sucursal-legacy-1'")
    conn.commit()

    vista = _vista(conn, sesion)
    _abrir_desde_cero(vista, "mp_processing_orders")

    assert vista.stack.currentWidget()._table.rowCount() == 0
    assert tragados.records, (
        "La pantalla quedo vacia por una identidad invalida y NO quedo rastro "
        "en el log: ese fallo seria invisible en produccion.")


# -- real vs placeholder, medido ronda a ronda ------------------------------
@pytest.mark.parametrize("page_id", PAGE_IDS)
def test_the_route_is_the_kind_of_page_we_think_it_is(app, conn, sesion,
                                                      dialogos, page_id):
    """28 de 29 rutas son el placeholder declarado; una es real.

    Se mide en vez de asumirse por lo que ya paso en este modulo: se juzgo
    sobre `build_page` —que devuelve placeholder siempre— y salio "las 29 son
    placeholder", incluida la que si tenia pagina.
    """
    vista = _vista(conn, sesion)
    _abrir_desde_cero(vista, page_id)
    pagina = vista.stack.currentWidget()

    es_placeholder = isinstance(pagina, MeatProcessingPlaceholderPage)
    if page_id in RUTAS_REALES:
        assert not es_placeholder, (
            f"{page_id} deberia tener pagina real y cayo al placeholder")
    else:
        assert es_placeholder, (
            f"{page_id} ya tiene pagina real ({type(pagina).__name__}); "
            "anadela a RUTAS_REALES para que el trinquete suba")


# -- el feature flag decide que se ve, no que exista ------------------------
def test_the_slaughter_routes_stay_out_of_the_sidebar(app, conn, sesion, dialogos):
    """Las 10 entradas de sacrificio estan tras `SLAUGHTER_ENABLED`, hoy en
    False. Que se oculten es el comportamiento buscado; que dejen de ocultarse
    sin que nadie lo note, no."""
    vista = _vista(conn, sesion)
    mostradas = {
        vista.sidebar.item(fila).data(0x0100)  # Qt.UserRole
        for fila in range(vista.sidebar.count())
    }

    if SLAUGHTER_ENABLED:
        assert mostradas == set(PAGE_IDS)
    else:
        assert mostradas == set(RUTAS_SIEMPRE)
        assert not (mostradas & RUTAS_TRAS_FLAG)


def test_a_user_without_permissions_sees_nothing(app, conn, dialogos):
    """Fail-closed (§23): el composition root niega todo sin sesion, y un
    usuario sin permisos no puede alcanzar ninguna ruta."""
    vista = _vista(conn, _Sesion(permisos=frozenset()))
    assert vista.sidebar.count() == 0
