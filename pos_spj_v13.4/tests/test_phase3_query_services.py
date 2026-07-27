import sqlite3

from core.services.sales.product_catalog_query_service import ProductCatalogQueryService
from core.services.sales.customer_lookup_service import CustomerLookupService


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE productos (id INTEGER, nombre TEXT, precio REAL, existencia REAL, unidad TEXT, categoria TEXT, stock_minimo REAL, imagen_path TEXT, es_compuesto INTEGER, es_subproducto INTEGER, codigo_barras TEXT, codigo TEXT, oculto INTEGER, activo INTEGER)")
    conn.execute("CREATE TABLE inventory_stock (product_id INTEGER, branch_id INTEGER, quantity REAL, unit TEXT)")
    conn.execute("CREATE TABLE clientes (id INTEGER, nombre TEXT, telefono TEXT, email TEXT, direccion TEXT, rfc TEXT, puntos INTEGER, codigo_qr TEXT, saldo REAL, nivel_fidelidad TEXT, activo INTEGER)")
    conn.execute("CREATE TABLE tarjetas_fidelidad (codigo TEXT, id_cliente INTEGER, activa INTEGER)")
    return conn


def test_product_catalog_query_service_lista_y_categorias():
    db = _db()
    db.execute("INSERT INTO productos VALUES (1,'Pollo',100,5,'kg','Carnes',1,'',0,0,'CB1','C1',0,1)")
    db.execute("INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (1,1,9,'kg')")
    svc = ProductCatalogQueryService(db)

    cats = svc.get_categories()
    assert 'Carnes' in cats

    rows = svc.list_visible_products(branch_id=1, filtro='Pollo', categoria='Carnes')
    assert len(rows) == 1
    assert rows[0]['nombre'] == 'Pollo'
    assert rows[0]['existencia'] == 9.0


def test_customer_lookup_service_busqueda_credito_loyalty():
    db = _db()
    db.execute("INSERT INTO clientes VALUES (7,'Ana','555','a@x.com','dir','RFC',25,'QR1',120.5,'Plata',1)")
    db.execute("INSERT INTO tarjetas_fidelidad VALUES ('CARD7',7,1)")

    svc = CustomerLookupService(db)
    rows = svc.buscar_cliente('Ana', limit=1)
    assert rows[0]['id'] == 7
    assert svc.get_credit_balance(7) == 120.5
    loyalty = svc.get_loyalty_status(7)
    assert loyalty['puntos'] == 25
    assert svc.get_by_loyalty_card('CARD7')['id'] == 7


def test_product_catalog_query_service_uses_inventory_stock_when_legacy_stock_differs():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE productos (id INTEGER, nombre TEXT, precio REAL, existencia REAL, unidad TEXT, categoria TEXT, stock_minimo REAL, imagen_path TEXT, es_compuesto INTEGER, es_subproducto INTEGER, codigo_barras TEXT, codigo TEXT, oculto INTEGER, activo INTEGER)")
    db.execute("CREATE TABLE inventory_stock (product_id INTEGER, branch_id INTEGER, quantity REAL, unit TEXT)")
    db.execute("CREATE TABLE branch_inventory (product_id INTEGER, branch_id INTEGER, quantity REAL)")
    db.execute("INSERT INTO productos VALUES (1,'Pollo',100,5,'kg','Carnes',1,'',0,0,'CB1','C1',0,1)")
    db.execute("INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (1,1,11,'kg')")
    db.execute("INSERT INTO branch_inventory(product_id, branch_id, quantity) VALUES (1,1,99)")

    rows = ProductCatalogQueryService(db).list_visible_products(branch_id=1, filtro='', categoria='')

    assert len(rows) == 1
    assert rows[0]['nombre'] == 'Pollo'
    assert rows[0]['existencia'] == 11.0


def test_product_catalog_query_service_returns_zero_without_inventory_stock_row():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE productos (id INTEGER, nombre TEXT, precio REAL, existencia REAL, unidad TEXT, categoria TEXT, stock_minimo REAL, imagen_path TEXT, es_compuesto INTEGER, es_subproducto INTEGER, codigo_barras TEXT, codigo TEXT, oculto INTEGER, activo INTEGER)")
    db.execute("INSERT INTO productos VALUES (1,'Pollo',100,5,'kg','Carnes',1,'',0,0,'CB1','C1',0,1)")

    rows = ProductCatalogQueryService(db).list_visible_products(branch_id=1, filtro='', categoria='')

    assert len(rows) == 1
    assert rows[0]['nombre'] == 'Pollo'
    assert rows[0]['existencia'] == 0.0
