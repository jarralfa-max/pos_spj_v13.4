"""Paso 2 — los consumidores dejan de tener buscador propio.

Dos migraciones distintas con la misma raíz:

1. **Merma** resolvía la búsqueda en su repositorio de infraestructura con SQL
   propio e INVÁLIDO (`products.active`, `products.sku`: columnas que el maestro
   canónico no tiene). Reventaba con `OperationalError` en cada tecla y la
   pantalla lo mostraba como "No se pudo consultar". Ahora recibe inyectado el
   preset canónico que ya tenía declarado.
2. **`ProductQueryService`** —el adaptador que sirve a Inventario y Cárnico—
   tenía su propio SQL, tercera variante viva del mismo "buscar producto".
   Ahora delega en `ProductSearchQuery`, con paridad de comportamiento.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_selection_query_service import (  # noqa: E402
    ProductCatalogSearchQueryService,
    ProductSearchQuery,
    SearchWasteEligibleProductsQueryService,
)
from backend.application.queries.product_query_service import ProductQueryService  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.losses.presenters.loss_registration_presenter import (  # noqa: E402
    LossRegistrationPresenter,
)
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402


def _product(conn, *, name, code, lifecycle="ACTIVE", inventory_managed=1):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed, "
        "internal_only) VALUES (?,?,?,?,?,?,?,1,1,?,0)",
        (pid, code, name, " ".join(name.strip().lower().split()), "RESALE_PRODUCT",
         lifecycle, "kg", inventory_managed))
    return pid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    return c


# ── Merma ─────────────────────────────────────────────────────────────────
def _presenter(conn, *, con_busqueda=True):
    busqueda = SearchWasteEligibleProductsQueryService(conn) if con_busqueda else None
    return LossRegistrationPresenter(object(), object(), lambda: None, busqueda)


def test_merma_encuentra_productos_de_verdad(conn):
    """La regresión que el SQL roto habría fallado: antes lanzaba
    `no such column: active` en vez de devolver nada."""
    pid = _product(conn, name="Pechuga", code="CAR-1")
    conn.commit()

    opciones = _presenter(conn).search_products("pechuga")

    assert [o.id for o in opciones] == [pid]
    assert opciones[0].label == "Pechuga"
    assert opciones[0].subtitle == "CAR-1"


def test_merma_busca_tambien_por_codigo(conn):
    pid = _product(conn, name="Pechuga", code="CAR-1")
    conn.commit()
    assert [o.id for o in _presenter(conn).search_products("CAR-1")] == [pid]


def test_merma_respeta_el_preset_y_excluye_borradores(conn):
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    _product(conn, name="No inventariable", code="N-1", inventory_managed=0)
    conn.commit()

    assert _presenter(conn).search_products("") == []


def test_merma_explica_por_que_no_hay_nada(conn):
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    conn.commit()

    razon = _presenter(conn).product_search_reason("")

    assert razon is not None and "activos" in razon.lower()


def test_merma_sin_busqueda_inyectada_no_truena(conn):
    presenter = _presenter(conn, con_busqueda=False)
    assert presenter.search_products("pechuga") == []
    assert presenter.product_search_reason("pechuga") is None


# ── ProductQueryService (Inventario + Cárnico) ────────────────────────────
def _barcode(conn, product_id, value):
    conn.execute(
        "INSERT INTO product_barcodes (id, product_id, barcode_value, barcode_type, "
        "is_primary, active) VALUES (?,?,?,?,1,1)",
        (new_uuid(), product_id, value, "EAN13"))


def test_product_query_service_mantiene_forma_y_paridad(conn):
    pid = _product(conn, name="Pollo Entero", code="PRD-1")
    conn.commit()

    resultados = ProductQueryService.from_connection(conn).search_products("pollo")

    assert [r.id for r in resultados] == [pid]
    assert resultados[0].label == "Pollo Entero"
    assert resultados[0].subtitle == "PRD-1"


def test_product_query_service_encuentra_por_codigo_de_barras(conn):
    pid = _product(conn, name="Pollo Entero", code="PRD-1")
    _barcode(conn, pid, "7501234567890")
    conn.commit()

    resultados = ProductQueryService.from_connection(conn).search_products("7501234567890")

    assert [r.id for r in resultados] == [pid]


def test_product_query_service_excluye_no_activos(conn):
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    conn.commit()

    assert ProductQueryService.from_connection(conn).search_products("borrador") == []


def test_product_query_service_sin_texto_devuelve_el_catalogo_activo(conn):
    _product(conn, name="Uno", code="U-1")
    _product(conn, name="Dos", code="D-1")
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    conn.commit()

    resultados = ProductQueryService.from_connection(conn).search_products("")

    assert {r.label for r in resultados} == {"Uno", "Dos"}


# ── selector del módulo de Productos ──────────────────────────────────────
def _products_presenter(conn, *, con_busqueda=True):
    return ProductsPresenter(
        read_service_factory=lambda: None,
        product_search_factory=(
            (lambda: ProductCatalogSearchQueryService(conn)) if con_busqueda else None))


def test_selector_de_productos_devuelve_la_forma_que_la_ui_espera(conn):
    """`branch_channel_page` lee r["code"]/r["name"]/r["id"]; el diálogo de
    recetas lo mismo. La migración no puede cambiar esas claves."""
    pid = _product(conn, name="Pechuga", code="CAR-1")
    conn.commit()

    filas = _products_presenter(conn).search_products_for_assignment(query="pechuga")

    assert filas == [{"id": pid, "code": "CAR-1", "name": "Pechuga",
                      "product_type": "RESALE_PRODUCT"}]


def test_selector_sigue_incluyendo_borradores_y_revision(conn):
    """Paridad deliberada: se asignan a sucursal y se usan como componentes
    ANTES de activarse. Filtrarlos sería un cambio de comportamiento."""
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    _product(conn, name="En revisión", code="R-1", lifecycle="UNDER_REVIEW")
    conn.commit()

    nombres = {f["name"] for f in
               _products_presenter(conn).search_products_for_assignment()}

    assert nombres == {"Borrador", "En revisión"}


def test_selector_sin_busqueda_inyectada_no_truena(conn):
    presenter = _products_presenter(conn, con_busqueda=False)
    assert presenter.search_products_for_assignment(query="x") == []
    assert presenter.product_search_reason("x") is None


def test_selector_explica_el_vacio(conn):
    razon = _products_presenter(conn).product_search_reason("")
    assert razon is not None and "catálogo" in razon.lower()


def test_la_composicion_de_productos_inyecta_la_busqueda_canonica():
    """Sin fallback en el presentador, olvidar el cableado dejaría el selector
    mudo — así que el cableado se verifica, no se supone.

    Se comprueban las DOS mitades: que se pase el parámetro y que el símbolo
    esté importado. Separarlas no es pedantería — al escribir esta migración se
    pasó el parámetro sin importar la clase, que es un `NameError` en tiempo de
    construcción y que un test del kwarg solo no habría visto.
    """
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[3]
    ruta = raiz / "frontend/desktop/modules/products/composition.py"
    fuente = ruta.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "ProductsPresenter"]
    assert llamadas, "No se encontró la construcción de ProductsPresenter"
    for llamada in llamadas:
        assert any(kw.arg == "product_search_factory" for kw in llamada.keywords), \
            "ProductsPresenter se construye sin product_search_factory"

    importados = {
        alias.name
        for nodo in ast.walk(arbol) if isinstance(nodo, ast.ImportFrom)
        for alias in nodo.names
    }
    assert "ProductCatalogSearchQueryService" in importados, \
        "composition.py usa la búsqueda canónica sin importarla (NameError al construir)"


# ── listado del catálogo, ya por el contrato ──────────────────────────────
def test_list_catalog_conserva_estado_y_carnico(conn):
    """`catalog_table` pinta columnas Estado y Cárnico: la migración no puede
    perderlas."""
    pid = _product(conn, name="Pechuga", code="CAR-1", lifecycle="UNDER_REVIEW")
    conn.commit()

    filas = ProductCatalogReadService(conn).list_catalog(query="pechuga")

    assert filas == [{"id": pid, "code": "CAR-1", "name": "Pechuga",
                      "product_type": "RESALE_PRODUCT",
                      "lifecycle_status": "UNDER_REVIEW", "is_meat": False}]


def test_list_catalog_sigue_mostrando_borradores(conn):
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    conn.commit()
    assert [f["name"] for f in ProductCatalogReadService(conn).list_catalog()] == ["Borrador"]


def test_list_catalog_ahora_tambien_encuentra_por_codigo_de_barras(conn):
    """Capacidad que gana al unificarse: su SQL propio no miraba barcodes."""
    pid = _product(conn, name="Pechuga", code="CAR-1")
    _barcode(conn, pid, "7501234567890")
    conn.commit()

    filas = ProductCatalogReadService(conn).list_catalog(query="7501234567890")

    assert [f["id"] for f in filas] == [pid]


def test_list_catalog_respeta_el_filtro_por_tipo(conn):
    _product(conn, name="Pechuga", code="CAR-1")
    conn.commit()
    assert ProductCatalogReadService(conn).list_catalog(
        product_type="RAW_MATERIAL") == []


def test_el_dto_canonico_transporta_el_estado(conn):
    _product(conn, name="Borrador", code="B-1", lifecycle="DRAFT")
    conn.commit()
    dtos = ProductCatalogSearchQueryService(conn).search(
        ProductSearchQuery(active_only=False))
    assert [d.lifecycle_status for d in dtos] == ["DRAFT"]


# ── estrechamiento autorizado de Inventario ───────────────────────────────
def test_inventario_ya_no_ofrece_productos_no_inventariables(conn):
    """Cambio de comportamiento deliberado: disponibilidad, lotes y reservas no
    significan nada para un producto que no controla existencia."""
    inventariable = _product(conn, name="Pechuga", code="CAR-1", inventory_managed=1)
    _product(conn, name="Servicio", code="SRV-1", inventory_managed=0)
    conn.commit()

    resultados = ProductQueryService.from_connection(conn).search_products("")

    assert [r.id for r in resultados] == [inventariable]


# ── el motivo del vacío llega a todas las pantallas ───────────────────────
_PANTALLAS_CON_SELECTOR = (
    "frontend/desktop/modules/products/dialogs/recipe_form_dialog.py",
    "frontend/desktop/modules/products/dialogs/cutting_form_dialog.py",
    "frontend/desktop/modules/products/dialogs/yield_form_dialog.py",
)


def test_los_selectores_de_productos_explican_el_vacio():
    """Cada `EntitySearchInput` de producto debe recibir el motivo; si no, la
    pantalla vuelve a decir sólo "Sin resultados"."""
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[3]
    faltantes = []
    for relativo in _PANTALLAS_CON_SELECTOR:
        arbol = ast.parse((raiz / relativo).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            if getattr(nodo.func, "id", None) != "EntitySearchInput":
                continue
            if not any(kw.arg == "empty_reason_provider" for kw in nodo.keywords):
                faltantes.append(f"{relativo.rsplit('/', 1)[-1]}:{nodo.lineno}")
    assert not faltantes, "Selector sin motivo del vacío: " + ", ".join(faltantes)


def test_la_pagina_de_sucursales_tambien_explica_el_vacio():
    """`branch_channel_page` pinta resultados en una TABLA, no en un
    `EntitySearchInput`, así que queda fuera del guard de arriba — y por eso
    mismo es donde el defecto reaparecería sin que nadie lo viera. Aquí se
    exige explícitamente que consulte el motivo.
    """
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[3]
    fuente = (raiz / "frontend/desktop/modules/products/pages/branch_channel_page.py"
              ).read_text(encoding="utf-8")

    assert "product_search_reason" in fuente, (
        "La página de sucursales/canales no consulta el motivo del vacío: "
        "una tabla vacía volvería a leerse como 'no existe'.")
