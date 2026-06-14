from __future__ import annotations

import sqlite3

from backend.application.commands.product_commands import CreateProductCommand, UpdateProductCommand
from backend.application.queries.product_query_service import ProductQueryService
from backend.application.services.product_catalog_service import ProductCatalogService
from backend.application.use_cases.create_product_use_case import CreateProductUseCase
from backend.application.use_cases.update_product_use_case import UpdateProductUseCase
from backend.domain.services.product_type_policy import ProductTypePolicy
from backend.infrastructure.db.repositories.product_repository import ProductRepository
from backend.shared.events.event_bus import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            codigo TEXT,
            codigo_barras TEXT,
            categoria TEXT,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            precio_minimo_venta REAL DEFAULT 0,
            unidad TEXT,
            stock_minimo REAL DEFAULT 0,
            tipo_producto TEXT,
            es_compuesto INTEGER DEFAULT 0,
            es_subproducto INTEGER DEFAULT 0,
            imagen_path TEXT,
            existencia REAL DEFAULT 0,
            oculto INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            ultima_actualizacion TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_product_id INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    return conn


def _service(conn: sqlite3.Connection, bus: InMemoryEventBus | None = None) -> ProductCatalogService:
    return ProductCatalogService(repository=ProductRepository(conn), event_bus=bus or InMemoryEventBus())


def _create_command(**overrides):
    data = dict(
        operation_id="op-product-1",
        branch_id="1",
        user_name="ana",
        name="Combo familiar",
        sku="P-COMBO",
        barcode="750000000001",
        category="Paquetes",
        sale_price=120.5,
        purchase_price=80.0,
        minimum_sale_price=90.0,
        unit="pza",
        minimum_stock=0.0,
        product_type="Compuesto",
    )
    data.update(overrides)
    return CreateProductCommand(**data)


def test_product_type_policy_extracts_rules_for_required_types() -> None:
    assert ProductTypePolicy.spanish_labels() == (
        "Simple",
        "Compuesto",
        "Procesable",
        "Subproducto",
        "Producido",
        "Insumo",
        "Servicio",
    )
    assert ProductTypePolicy.rules_for("Compuesto").allows_recipe is True
    assert ProductTypePolicy.rules_for("Compuesto").deducts_components_on_sale is True
    assert ProductTypePolicy.rules_for("Servicio").is_inventory_tracked is False
    assert ProductTypePolicy.rules_for("Subproducto").is_byproduct is True


def test_create_product_use_case_persists_zero_inventory_and_emits_event() -> None:
    conn = _db()
    bus = InMemoryEventBus()
    events = []
    bus.subscribe(EventName.PRODUCT_CREATED, events.append)

    result = CreateProductUseCase(app_service=_service(conn, bus)).execute(_create_command())

    assert result.success is True
    assert result.message == "PRODUCT_CREATED"
    assert result.data["recipe_pending"] is True
    row = conn.execute("SELECT * FROM productos WHERE id=?", (result.entity_id,)).fetchone()
    assert row["nombre"] == "Combo familiar"
    assert row["tipo_producto"] == "compuesto"
    assert row["es_compuesto"] == 1
    assert row["existencia"] == 0
    assert len(events) == 1
    assert events[0].operation_id == "op-product-1"
    assert events[0].payload["recipe_pending"] is True


def test_update_product_use_case_keeps_inventory_untouched() -> None:
    conn = _db()
    conn.execute(
        """
        INSERT INTO productos(nombre, codigo, categoria, precio, precio_compra, unidad, stock_minimo, tipo_producto, existencia, activo)
        VALUES ('Harina', 'HAR', 'Insumos', 10, 4, 'kg', 0, 'insumo', 25, 1)
        """
    )
    conn.commit()

    command = UpdateProductCommand(
        operation_id="op-update-product",
        branch_id="1",
        user_name="ana",
        product_id=1,
        name="Harina premium",
        sku="HAR",
        category="Insumos",
        sale_price=11,
        purchase_price=5,
        unit="kg",
        product_type="Insumo",
    )
    result = UpdateProductUseCase(app_service=_service(conn)).execute(command)

    assert result.success is True
    row = conn.execute("SELECT nombre, existencia, tipo_producto FROM productos WHERE id=1").fetchone()
    assert row["nombre"] == "Harina premium"
    assert row["existencia"] == 25
    assert row["tipo_producto"] == "insumo"


def test_product_query_service_supplies_search_and_categories_for_ui() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO productos(nombre, codigo, categoria, precio, unidad, tipo_producto, activo) VALUES ('Arrachera', 'ARR', 'Carnes', 150, 'kg', 'simple', 1)"
    )
    conn.commit()

    service = ProductQueryService.from_connection(conn)

    assert service.list_categories() == ["Carnes"]
    result = service.search_products("arr")
    assert result[0].label == "Arrachera"
    assert result[0].metadata["unit"] == "kg"
