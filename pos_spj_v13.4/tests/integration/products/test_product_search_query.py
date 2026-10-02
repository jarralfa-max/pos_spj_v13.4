"""Contrato único de búsqueda de productos (`ProductSearchQuery`).

Cubre lo que el contrato añade sobre el buscador anterior: código de barras
(parcial por texto, exacto por `barcode`), `sku` -> `code`, paginación
`page`/`page_size`, presets que sólo AÑADEN restricciones, y `with_stock_only`
resuelto por puerto inyectado en vez de por un JOIN a Inventario.

La retrocompatibilidad de los kwargs históricos se prueba aquí también: siete
consumidores siguen llamando `search(query=..., limit=..., offset=...)`.
"""

import sqlite3

import pytest

from backend.application.products.queries.product_selection_query_service import (
    ProductCatalogSearchQueryService,
    ProductSearchQuery,
    ProductSelectionDTO,
    SearchInventoryManagedProductsQueryService,
    SearchPurchasableProductsQueryService,
    SearchSellableProductsQueryService,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid


def _product(conn, *, name, code, sellable=1, purchasable=1, inventory_managed=1,
             internal_only=0, lifecycle="ACTIVE", ptype="RESALE_PRODUCT"):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed, "
        "internal_only) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pid, code, name, " ".join(name.strip().lower().split()), ptype, lifecycle,
         "kg", sellable, purchasable, inventory_managed, internal_only))
    return pid


def _barcode(conn, product_id, value, *, active=1):
    conn.execute(
        "INSERT INTO product_barcodes (id, product_id, barcode_value, barcode_type, "
        "is_primary, active) VALUES (?,?,?,?,1,?)",
        (new_uuid(), product_id, value, "EAN13", active))


def _habilitar(conn, product_id, branch_id):
    """`branch_id` en el contrato significa "habilitado en esta sucursal" (el
    JOIN a `branch_product`), y con `with_stock_only` es además la sucursal
    cuyo saldo se consulta. Tener existencia donde el producto no está
    habilitado no lo vuelve vendible ahí, así que ambas condiciones aplican."""
    conn.execute(
        "INSERT INTO branch_product (id, product_id, branch_id, enabled) "
        "VALUES (?,?,?,1)", (new_uuid(), product_id, branch_id))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    return c


class _Saldo:
    def __init__(self, available):
        self.available = available


class _FakeStockPort:
    """Lo que Inventario expone; Productos sólo ve este contrato."""

    def __init__(self, disponibles: dict[str, int]):
        self._disponibles = disponibles
        self.llamadas: list[tuple] = []

    def get_availability(self, *, product_id, branch_id, warehouse_id=None):
        self.llamadas.append((product_id, branch_id, warehouse_id))
        return _Saldo(self._disponibles.get(product_id, 0))


# ── código de barras / sku ────────────────────────────────────────────────
def test_barcode_exacto_no_acepta_parciales(conn):
    pid = _product(conn, name="Refresco", code="R1")
    _barcode(conn, pid, "7501234567890")
    conn.commit()
    svc = ProductCatalogSearchQueryService(conn)

    exacto = svc.search(ProductSearchQuery(barcode="7501234567890"))
    assert [r.product_id for r in exacto] == [pid]
    assert svc.search(ProductSearchQuery(barcode="750123")) == []


def test_barcode_inactivo_no_resuelve(conn):
    pid = _product(conn, name="Refresco", code="R1")
    _barcode(conn, pid, "7501234567890", active=0)
    conn.commit()
    assert ProductCatalogSearchQueryService(conn).search(
        ProductSearchQuery(barcode="7501234567890")) == []


def test_texto_busca_nombre_codigo_y_barras(conn):
    por_nombre = _product(conn, name="Pollo entero", code="AAA")
    por_codigo = _product(conn, name="Res molida", code="POLLO-9")
    por_barras = _product(conn, name="Cerdo", code="CCC")
    _barcode(conn, por_barras, "POLLO123")
    conn.commit()
    svc = ProductCatalogSearchQueryService(conn)

    encontrados = {r.product_id for r in svc.search(ProductSearchQuery(text="pollo"))}
    assert encontrados == {por_nombre, por_codigo, por_barras}


def test_texto_encuentra_filas_con_normalizado_vacio(conn):
    """Regresión: el buscador anterior miraba `p.name`. Hay filas viejas con
    `name_normalized` en el default vacío del esquema; perderlas sería peor
    que el problema que el contrato viene a resolver."""
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable) VALUES (?,?,?,'',?,?,?,1)",
        (pid, "OLD1", "Producto viejo", "RESALE_PRODUCT", "ACTIVE", "kg"))
    conn.commit()
    res = ProductCatalogSearchQueryService(conn).search(
        ProductSearchQuery(text="viejo"))
    assert [r.product_id for r in res] == [pid]


def test_sku_es_el_code_del_maestro_y_es_exacto(conn):
    pid = _product(conn, name="Refresco", code="SKU-1")
    _product(conn, name="Otro", code="SKU-10")
    conn.commit()
    svc = ProductCatalogSearchQueryService(conn)
    assert [r.product_id for r in svc.search(ProductSearchQuery(sku="SKU-1"))] == [pid]


# ── paginación ────────────────────────────────────────────────────────────
def test_paginacion_por_page_y_page_size(conn):
    for i in range(5):
        _product(conn, name=f"Pollo {i}", code=f"K{i}")
    conn.commit()
    svc = ProductCatalogSearchQueryService(conn)

    p1 = svc.search(ProductSearchQuery(text="pollo", page=1, page_size=2))
    p2 = svc.search(ProductSearchQuery(text="pollo", page=2, page_size=2))
    p3 = svc.search(ProductSearchQuery(text="pollo", page=3, page_size=2))
    assert [r.name for r in p1] == ["Pollo 0", "Pollo 1"]
    assert [r.name for r in p2] == ["Pollo 2", "Pollo 3"]
    assert [r.name for r in p3] == ["Pollo 4"]


def test_page_invalida_falla_ruidosamente():
    with pytest.raises(ValueError):
        ProductSearchQuery(page=0)
    with pytest.raises(ValueError):
        ProductSearchQuery(page_size=0)


# ── presets: los módulos sólo añaden restricciones ────────────────────────
def test_preset_de_ventas_restringe_aunque_el_criterio_no_lo_pida(conn):
    _product(conn, name="Vendible", code="V1", sellable=1)
    _product(conn, name="No vendible", code="V2", sellable=0)
    _product(conn, name="Interno", code="V3", sellable=1, internal_only=1)
    _product(conn, name="Borrador", code="V4", lifecycle="DRAFT")
    conn.commit()

    res = SearchSellableProductsQueryService(conn).search(ProductSearchQuery())
    assert {r.name for r in res} == {"Vendible"}
    assert all(isinstance(r, ProductSelectionDTO) for r in res)


def test_presets_distintos_sobre_el_mismo_contrato(conn):
    _product(conn, name="Sólo comprable", code="X1", sellable=0, purchasable=1)
    _product(conn, name="Sólo vendible", code="X2", sellable=1, purchasable=0)
    conn.commit()
    criterio = ProductSearchQuery()

    compras = {r.name for r in SearchPurchasableProductsQueryService(conn).search(criterio)}
    ventas = {r.name for r in SearchSellableProductsQueryService(conn).search(criterio)}
    assert compras == {"Sólo comprable"}
    assert ventas == {"Sólo vendible"}


def test_restrict_solo_aprieta_nunca_afloja():
    base = ProductSearchQuery(sellable_only=True, active_only=True)
    relajado = base.restrict(sellable_only=False, active_only=False)
    assert relajado.sellable_only is True
    assert relajado.active_only is True
    assert base.restrict(purchasable_only=True).purchasable_only is True


def test_restrict_no_muta_el_original():
    base = ProductSearchQuery(text="pollo")
    base.restrict(branch_id="b1")
    assert base.branch_id is None


# ── with_stock_only: por puerto, nunca por JOIN a Inventario ──────────────
def test_with_stock_only_sin_puerto_falla_ruidosamente(conn):
    _product(conn, name="Refresco", code="R1")
    conn.commit()
    with pytest.raises(ValueError, match="stock_port"):
        ProductCatalogSearchQueryService(conn).search(
            ProductSearchQuery(with_stock_only=True, branch_id="b1"))


def test_with_stock_only_exige_sucursal(conn):
    with pytest.raises(ValueError, match="branch_id"):
        ProductCatalogSearchQueryService(
            conn, stock_port=_FakeStockPort({})).search(
                ProductSearchQuery(with_stock_only=True))


def test_with_stock_only_filtra_por_el_puerto(conn):
    con = _product(conn, name="Con existencia", code="S1")
    sin = _product(conn, name="Sin existencia", code="S2")
    _habilitar(conn, con, "b1")
    _habilitar(conn, sin, "b1")
    conn.commit()
    port = _FakeStockPort({con: 5})

    res = ProductCatalogSearchQueryService(conn, stock_port=port).search(
        ProductSearchQuery(with_stock_only=True, branch_id="b1", warehouse_id="w1"))

    assert [r.product_id for r in res] == [con]
    assert ("b1", "w1") == port.llamadas[0][1:]


def test_with_stock_only_pagina_despues_de_filtrar(conn):
    """Filtrar después de paginar en SQL devolvería páginas cortas sin avisar."""
    ids = []
    for i in range(4):
        ids.append(_product(conn, name=f"Prod {i}", code=f"P{i}"))
        _habilitar(conn, ids[-1], "b1")
    conn.commit()
    # sólo 0 y 3 tienen existencia: la página 1 de tamaño 2 debe traer ambos
    port = _FakeStockPort({ids[0]: 1, ids[3]: 1})

    res = ProductCatalogSearchQueryService(conn, stock_port=port).search(
        ProductSearchQuery(with_stock_only=True, branch_id="b1",
                           page=1, page_size=2))
    assert [r.name for r in res] == ["Prod 0", "Prod 3"]


# ── retrocompatibilidad ───────────────────────────────────────────────────
def test_kwargs_historicos_siguen_funcionando(conn):
    for i in range(3):
        _product(conn, name=f"Pollo {i}", code=f"K{i}")
    _product(conn, name="Res", code="R9")
    conn.commit()
    svc = SearchSellableProductsQueryService(conn)

    assert {r.name for r in svc.search(query="Pollo")} == {f"Pollo {i}" for i in range(3)}
    assert len(svc.search(query="Pollo", limit=2, offset=0)) == 2
    assert [r.name for r in svc.search(query="Pollo", limit=2, offset=2)] == ["Pollo 2"]


def test_no_se_mezclan_contrato_y_kwargs(conn):
    with pytest.raises(TypeError):
        ProductCatalogSearchQueryService(conn).search(
            ProductSearchQuery(text="x"), query="y")


# ── base sin índice de códigos de barras ──────────────────────────────────
@pytest.fixture
def conn_sin_barcodes():
    """Sólo `products`. Hay fixtures y bases viejas así; la búsqueda por texto
    funcionaba antes porque no tocaba `product_barcodes`, y debe seguir
    funcionando."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE products (
            id TEXT PRIMARY KEY, code TEXT, name TEXT, name_normalized TEXT,
            short_name TEXT, product_type TEXT, lifecycle_status TEXT,
            base_unit_id TEXT, species_id TEXT, category_id TEXT,
            catch_weight_enabled INTEGER DEFAULT 0, lot_controlled INTEGER DEFAULT 0,
            inventory_managed INTEGER DEFAULT 1, sellable INTEGER DEFAULT 1,
            purchasable INTEGER DEFAULT 1, producible INTEGER DEFAULT 0,
            internal_only INTEGER DEFAULT 0)
    """)
    c.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id) VALUES ('p1','R1','Refresco','refresco',"
        "'RESALE_PRODUCT','ACTIVE','kg')")
    c.commit()
    return c


def test_texto_funciona_sin_tabla_de_barcodes(conn_sin_barcodes):
    res = ProductCatalogSearchQueryService(conn_sin_barcodes).search(
        ProductSearchQuery(text="refresco"))
    assert [r.product_id for r in res] == ["p1"]


def test_barcode_sin_tabla_no_devuelve_el_catalogo_entero(conn_sin_barcodes):
    """Ignorar el filtro ante un escaneo sería peor que no encontrar nada."""
    res = ProductCatalogSearchQueryService(conn_sin_barcodes).search(
        ProductSearchQuery(barcode="7501234567890"))
    assert res == []


# ── base sin la columna `name_normalized` ─────────────────────────────────
@pytest.fixture
def conn_sin_normalizado():
    """Forma real de varios fixtures vivos (los presentadores de BI, p. ej.):
    `products` sin `name_normalized` ni `product_barcodes`. El buscador
    anterior funcionaba aquí porque sólo miraba `p.name`/`p.code`."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, "
        "short_name TEXT, product_type TEXT, base_unit_id TEXT, species_id TEXT, "
        "catch_weight_enabled INTEGER, lot_controlled INTEGER, "
        "inventory_managed INTEGER, sellable INTEGER, purchasable INTEGER, "
        "producible INTEGER, internal_only INTEGER, lifecycle_status TEXT)")
    c.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status, "
        "sellable, internal_only) VALUES ('p1','R1','Refresco','RESALE_PRODUCT',"
        "'ACTIVE',1,0)")
    c.commit()
    return c


# ── base con un `products` REDUCIDO ───────────────────────────────────────
@pytest.fixture
def conn_minimo():
    """Forma exacta del fixture vivo de `test_inventory_quarantine_open`: sin
    `short_name`, sin `name_normalized` y SIN NINGUNA bandera de capacidad.

    Es el caso que rompió al migrar Inventario al contrato: el `SELECT` pedía
    columnas inexistentes, saltaba `OperationalError` y el presentador lo
    convertía en `[]` — búsqueda vacía en silencio.
    """
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, code TEXT, "
        "category_id TEXT, base_unit_id TEXT, "
        "lifecycle_status TEXT DEFAULT 'ACTIVE', product_type TEXT)")
    c.execute(
        "INSERT INTO products (id, name, code, base_unit_id, lifecycle_status) "
        "VALUES ('p1','Pechuga de pollo','POLLO-001','kg','ACTIVE')")
    c.commit()
    return c


def test_busqueda_sobrevive_a_un_products_reducido(conn_minimo):
    svc = SearchInventoryManagedProductsQueryService(conn_minimo)

    por_nombre = svc.search(ProductSearchQuery(text="pechuga"))
    por_codigo = svc.search(ProductSearchQuery(text="POLLO-001"))

    assert [r.product_id for r in por_nombre] == ["p1"]
    assert [r.product_id for r in por_codigo] == ["p1"]


def test_el_preset_se_omite_si_la_columna_no_existe(conn_minimo):
    """Sin columna `inventory_managed` el filtro no puede aplicarse. Se omite —
    el esquema es anterior al concepto— en vez de devolver cero: para un
    selector, de más es mucho menos dañino que nada."""
    assert len(SearchInventoryManagedProductsQueryService(conn_minimo).search(
        ProductSearchQuery())) == 1


def test_las_columnas_ausentes_llegan_como_valores_seguros(conn_minimo):
    dto = SearchInventoryManagedProductsQueryService(conn_minimo).search(
        ProductSearchQuery())[0]

    assert dto.short_name is None
    assert dto.inventory_managed is False and dto.sellable is False
    assert dto.name == "Pechuga de pollo" and dto.code == "POLLO-001"


def test_texto_funciona_sin_columna_normalizada(conn_sin_normalizado):
    svc = SearchSellableProductsQueryService(conn_sin_normalizado)
    assert [r.product_id for r in svc.search(ProductSearchQuery(text="refresco"))] == ["p1"]
    assert [r.product_id for r in svc.search(ProductSearchQuery(text="R1"))] == ["p1"]


def test_sin_coincidencia_devuelve_vacio_no_error(conn_sin_normalizado):
    assert SearchSellableProductsQueryService(conn_sin_normalizado).search(
        ProductSearchQuery(text="inexistente")) == []


# ── por qué está vacío: cero resultados NO es una sola causa ──────────────
def test_explica_catalogo_vacio(conn):
    razon = ProductCatalogSearchQueryService(conn).explain_empty(ProductSearchQuery())
    assert razon.code == "SIN_CATALOGO"


def test_explica_que_no_hay_activos(conn):
    _product(conn, name="Alas", code="CAR-1", lifecycle="UNDER_REVIEW")
    conn.commit()
    razon = ProductCatalogSearchQueryService(conn).explain_empty(ProductSearchQuery())
    assert razon.code == "SIN_ACTIVOS"


def test_explica_que_nada_esta_habilitado_en_la_sucursal(conn):
    """El caso real medido en la base viva: producto ACTIVE que no tiene
    ninguna fila en `branch_product`, así que toda búsqueda con sucursal da
    cero y antes se veía igual que 'no existe'."""
    _product(conn, name="Pollo Entero", code="PRD-1")
    conn.commit()
    razon = ProductCatalogSearchQueryService(conn).explain_empty(
        ProductSearchQuery(branch_id="b1"))
    assert razon.code == "SIN_HABILITAR_EN_SUCURSAL"
    assert "Sucursales y surtidos" in razon.message


def test_explica_que_el_termino_no_coincide(conn):
    pid = _product(conn, name="Pollo Entero", code="PRD-1")
    _habilitar(conn, pid, "b1")
    conn.commit()
    razon = ProductCatalogSearchQueryService(conn).explain_empty(
        ProductSearchQuery(text="tornillo", branch_id="b1"))
    assert razon.code == "NO_COINCIDE"


def test_lo_buscado_existe_pero_no_esta_habilitado_aunque_haya_otros(conn):
    """Medido 2026-09-25 en la base real: en Corregidora sólo «Alas» estaba
    habilitado; buscar «pechuga» respondía "ninguno coincide" porque la
    explicación relajaba primero el TEXTO. La causa real es la habilitación."""
    alas = _product(conn, name="Alas", code="CAR-1")
    _product(conn, name="Pechuga", code="CAR-4")
    _habilitar(conn, alas, "b1")
    conn.commit()
    razon = SearchPurchasableProductsQueryService(conn).explain_empty(
        ProductSearchQuery(text="pechuga", branch_id="b1"))
    assert razon.code == "SIN_HABILITAR_EN_SUCURSAL"
    assert "Sucursales y surtidos" in razon.message


def test_lo_buscado_existe_pero_no_esta_activo(conn):
    alas = _product(conn, name="Alas", code="CAR-1")
    _product(conn, name="Pechuga", code="CAR-4", lifecycle="UNDER_REVIEW")
    _habilitar(conn, alas, "b1")
    conn.commit()
    razon = SearchPurchasableProductsQueryService(conn).explain_empty(
        ProductSearchQuery(text="pechuga", branch_id="b1"))
    assert razon.code == "SIN_ACTIVOS"


def test_no_explica_nada_cuando_si_hay_resultados(conn):
    pid = _product(conn, name="Pollo Entero", code="PRD-1")
    _habilitar(conn, pid, "b1")
    conn.commit()
    assert ProductCatalogSearchQueryService(conn).explain_empty(
        ProductSearchQuery(text="pollo", branch_id="b1")) is None


def test_explica_falta_de_existencia(conn):
    pid = _product(conn, name="Pollo Entero", code="PRD-1")
    _habilitar(conn, pid, "b1")
    conn.commit()
    svc = ProductCatalogSearchQueryService(conn, stock_port=_FakeStockPort({}))
    criterio = ProductSearchQuery(with_stock_only=True, branch_id="b1")
    assert svc.search(criterio) == []
    assert svc.explain_empty(criterio).code == "SIN_EXISTENCIA"


def test_el_preset_del_modulo_cuenta_para_la_explicacion(conn):
    """Compras no debe decir 'no hay catálogo' cuando lo que pasa es que nada
    es comprable."""
    _product(conn, name="Sólo vendible", code="V1", sellable=1, purchasable=0)
    conn.commit()
    razon = SearchPurchasableProductsQueryService(conn).explain_empty(ProductSearchQuery())
    assert razon.code == "SIN_CATALOGO"
