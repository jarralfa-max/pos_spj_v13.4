# tests/test_catalog_hot_refresh.py — SPJ POS v13.4
"""
F12 — Propagación en caliente de catálogos (sucursales/productos) y
corrección del error de tipos en Compras.

Bugs cubiertos:
  1. Crear sucursal no emitía eventos → módulos requerían reinicio.
  2. list_active_branches consultaba una columna inexistente (`activo`) y
     Compras caía al fallback 'Sucursal Principal' con id entero 1.
  3. Crear producto vía ProductCatalogService no publicaba nada al bus.
  4. `'<=' not supported between instances of 'str' and 'int'` en
     _procesar_compra (validaciones numéricas sobre IDs UUID en el UC).

PyQt5 no está disponible en CI: los widgets se simulan con fakes que
implementan el mismo contrato (on_branches_changed / refresh_branches /
refresh_products / actualizar_datos); el cableado PyQt se verifica por
aserciones de código fuente.
"""
import os
import sqlite3

import pytest

from backend.shared.ids import new_uuid
from core.events.event_bus import get_bus
from core.events.domain_events import (
    BRANCH_CREATED,
    BRANCH_DEACTIVATED,
    BRANCHES_CHANGED,
    PRODUCT_CREATED,
    PRODUCTS_CHANGED,
)
from core.events.catalog_events import (
    fan_out_branches_changed,
    fan_out_products_changed,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relpath: str) -> str:
    with open(os.path.join(_ROOT, relpath), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def catalog_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE sucursales (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
            direccion TEXT, telefono TEXT,
            hora_apertura TEXT, hora_cierre TEXT, dias_operacion TEXT,
            acepta_pedidos_fuera_horario INTEGER DEFAULT 0,
            mensaje_fuera_horario TEXT,
            activa INTEGER DEFAULT 1,
            fecha_alta TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, codigo TEXT,
            codigo_barras TEXT, categoria TEXT, precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0, precio_minimo_venta REAL DEFAULT 0,
            unidad TEXT, stock_minimo REAL DEFAULT 0, tipo_producto TEXT,
            es_compuesto INTEGER DEFAULT 0, es_subproducto INTEGER DEFAULT 0,
            imagen_path TEXT, existencia REAL DEFAULT 0,
            oculto INTEGER DEFAULT 0, activo INTEGER DEFAULT 1
        );
    """)
    yield conn
    conn.close()


@pytest.fixture
def bus_recorder():
    """Captura eventos del bus singleton y limpia las suscripciones al salir."""
    bus = get_bus()
    captured: list[tuple[str, dict]] = []
    subscribed: list[tuple[str, object]] = []

    def listen(*event_types):
        for evt in event_types:
            def handler(data, _evt=evt):
                captured.append((_evt, data))
            bus.subscribe(_evt := evt, handler, label=f"test_capture_{evt}_{id(handler)}")
            subscribed.append((evt, handler))
        return captured

    yield listen
    for evt, handler in subscribed:
        try:
            bus.unsubscribe(evt, handler)
        except Exception:
            pass


class FakeConHandler:
    def __init__(self):
        self.payloads = []

    def on_branches_changed(self, payload):
        self.payloads.append(payload)


class FakeConRefresh:
    def __init__(self):
        self.calls = 0

    def refresh_branches(self):
        self.calls += 1


class FakeProductoWidget:
    def __init__(self):
        self.refreshed = 0

    def refresh_products(self):
        self.refreshed += 1


class FakeLegacyWidget:
    def __init__(self):
        self.actualizados = 0

    def actualizar_datos(self):
        self.actualizados += 1


# ── Test 1: crear/editar/desactivar sucursal emite eventos ───────────────────

def test_save_branch_emits_branch_created_and_branches_changed(catalog_db, bus_recorder):
    from core.services.configuration_settings_service import CompanyProfileService
    from repositories.config_repository import ConfigRepository

    captured = bus_recorder(BRANCH_CREATED, BRANCHES_CHANGED, BRANCH_DEACTIVATED)
    svc = CompanyProfileService(ConfigRepository(catalog_db))

    branch_id = svc.save_branch(
        name="Cadenas", address="Av. 1", phone="", active=True)

    tipos = [t for t, _ in captured]
    assert BRANCH_CREATED in tipos
    assert BRANCHES_CHANGED in tipos
    payload = next(d for t, d in captured if t == BRANCH_CREATED)
    assert payload["branch_id"] == str(branch_id)
    assert payload["branch_name"] == "Cadenas"
    assert payload["action"] == "created"
    assert payload["active"] is True
    assert payload["event_id"] and payload["operation_id"] and payload["timestamp"]

    # Desactivar → branch_deactivated + branches_changed
    captured.clear()
    svc.save_branch(name="Cadenas", address="Av. 1", phone="",
                    active=False, branch_id=branch_id)
    tipos = [t for t, _ in captured]
    assert BRANCH_DEACTIVATED in tipos and BRANCHES_CHANGED in tipos


def test_save_branch_delivery_profile_emits_events(catalog_db, bus_recorder):
    from core.services.configuration_settings_service import CompanyProfileService
    from repositories.config_repository import ConfigRepository

    captured = bus_recorder(BRANCH_CREATED, BRANCHES_CHANGED)
    svc = CompanyProfileService(ConfigRepository(catalog_db))
    branch_id = svc.save_branch_delivery_profile(
        name="Sur", address=None, phone=None, opening_time="09:00",
        closing_time="18:00", operation_days="1,2,3",
        accepts_after_hours_orders=False, after_hours_message="")
    tipos = [t for t, _ in captured]
    assert BRANCH_CREATED in tipos and BRANCHES_CHANGED in tipos
    assert any(d["branch_id"] == str(branch_id) for _, d in captured)


# ── Test 2: fan-out de BRANCHES_CHANGED (contrato MainWindow) ────────────────

def test_fan_out_branches_changed_calls_both_contract_variants():
    handler = FakeConHandler()
    refresher = FakeConRefresh()
    otro = object()  # sin contrato: se ignora sin fallar
    payload = {"action": "created", "branch_id": new_uuid()}

    notified = fan_out_branches_changed([handler, refresher, otro], payload)

    assert handler.payloads == [payload]
    assert refresher.calls == 1
    assert notified == [handler, refresher]


def test_main_window_subscribes_and_fans_out_catalog_events():
    src = _read("interfaz/main_window.py")
    assert "_suscribir_eventos_catalogo" in src
    assert "BRANCHES_CHANGED" in src and "PRODUCTS_CHANGED" in src
    assert "fan_out_branches_changed" in src
    assert "fan_out_products_changed" in src
    # Handler del bus salta al hilo Qt (el bus puede despachar en background).
    assert "QTimer.singleShot(0, lambda: self._on_branches_changed(data))" in src


# ── Test 3: Compras ve la sucursal nueva sin reinicio ─────────────────────────

def test_compras_sees_new_branch_after_event(catalog_db, bus_recorder):
    """Simula el ciclo completo: sucursal A visible → se crea B → evento →
    el 'widget' de compras recarga desde el repo y ve A y B."""
    from backend.infrastructure.db.repositories.compras_read_repository import (
        ComprasReadRepository,
    )
    from core.services.configuration_settings_service import CompanyProfileService
    from repositories.config_repository import ConfigRepository

    svc = CompanyProfileService(ConfigRepository(catalog_db))
    svc.save_branch(name="Sucursal A", address=None, phone=None, active=True)

    repo = ComprasReadRepository(catalog_db)

    class FakeCompras:
        def __init__(self):
            self.branch_names: list[str] = []
            self.refresh_branches()

        def refresh_branches(self):
            self.branch_names = [b["nombre"] for b in repo.list_active_branches()]

        def on_branches_changed(self, payload):
            self.refresh_branches()

    compras = FakeCompras()
    assert compras.branch_names == ["Sucursal A"]

    bus = get_bus()
    bus.subscribe(BRANCHES_CHANGED, compras.on_branches_changed,
                  label="test_fake_compras")
    try:
        svc.save_branch(name="Sucursal B", address=None, phone=None, active=True)
        assert sorted(compras.branch_names) == ["Sucursal A", "Sucursal B"]
    finally:
        bus.unsubscribe(BRANCHES_CHANGED, compras.on_branches_changed)
    # PUR-13: la aserción sobre el fuente del monolito se retiró (compras_pro es
    # ahora un wrapper canónico). El contrato de refresco por evento se valida
    # arriba con el repo canónico ComprasReadRepository.


# ── Test 4: crear producto emite eventos (incluye legacy) ────────────────────

def test_create_product_emits_product_created_products_changed_and_legacy(
        catalog_db, bus_recorder):
    from backend.application.services.product_catalog_service import (
        ProductCatalogService,
    )

    captured = bus_recorder(PRODUCT_CREATED, PRODUCTS_CHANGED, "PRODUCTO_CREADO")

    class Cmd:
        operation_id = new_uuid()
        branch_id = new_uuid()
        user_name = "tester"
        name = "Arrachera"
        sku = None
        code = None
        barcode = ""
        category = "Carnes"
        sale_price = 250.0
        price = 250.0
        purchase_price = 180.0
        minimum_sale_price = 0.0
        unit = "kg"
        minimum_stock = 1.0
        stock_minimum = 1.0
        product_type = "simple"
        image_path = None
        active = True

    result = ProductCatalogService(catalog_db).create_product(Cmd())
    assert result.success

    tipos = [t for t, _ in captured]
    assert PRODUCT_CREATED in tipos
    assert PRODUCTS_CHANGED in tipos
    assert "PRODUCTO_CREADO" in tipos          # canal legacy
    payload = next(d for t, d in captured if t == PRODUCT_CREATED)
    assert payload["product_id"] == str(result.entity_id)
    assert payload["product_name"] == "Arrachera"
    assert payload["action"] == "created"
    legacy = next(d for t, d in captured if t == "PRODUCTO_CREADO")
    assert legacy["producto_id"] == str(result.entity_id)


# ── Test 5: Inventario ve el producto nuevo sin reinicio ─────────────────────

def test_inventario_sees_new_product_after_event(catalog_db, bus_recorder):
    pytest.skip("INV-27: inventario_local eliminado; refresh en vivo no portado a la UI enterprise de solo lectura")
    from backend.application.services.product_catalog_service import (
        ProductCatalogService,
    )

    def _crear(nombre):
        class Cmd:
            operation_id = new_uuid()
            branch_id = ""
            user_name = "tester"
            name = nombre
            sku = None
            code = None
            barcode = ""
            category = ""
            sale_price = 10.0
            price = 10.0
            purchase_price = 5.0
            minimum_sale_price = 0.0
            unit = "kg"
            minimum_stock = 0.0
            stock_minimum = 0.0
            product_type = "simple"
            image_path = None
            active = True
        return ProductCatalogService(catalog_db).create_product(Cmd())

    _crear("Producto A")

    class FakeInventario:
        def __init__(self):
            self.product_names: list[str] = []
            self.refresh_products()

        def refresh_products(self):
            rows = catalog_db.execute(
                "SELECT nombre FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            self.product_names = [r[0] for r in rows]

        def on_products_changed(self, payload):
            self.refresh_products()

    inv = FakeInventario()
    assert inv.product_names == ["Producto A"]

    bus = get_bus()
    bus.subscribe(PRODUCTS_CHANGED, inv.on_products_changed,
                  label="test_fake_inventario")
    try:
        _crear("Producto B")
        assert inv.product_names == ["Producto A", "Producto B"]
    finally:
        bus.unsubscribe(PRODUCTS_CHANGED, inv.on_products_changed)

    # El módulo real implementa el contrato y escucha los eventos canónicos.
    src = _read("modulos/inventario_local.py")
    for needle in ("def refresh_products", "def on_products_changed",
                   "PRODUCTS_CHANGED"):
        assert needle in src, needle


def test_fan_out_products_changed_priority_and_fallback():
    especifico = FakeProductoWidget()
    legacy = FakeLegacyWidget()

    class Ambos(FakeProductoWidget, FakeLegacyWidget):
        def __init__(self):
            FakeProductoWidget.__init__(self)
            FakeLegacyWidget.__init__(self)

    ambos = Ambos()
    fan_out_products_changed([especifico, legacy, ambos], {"action": "created"})
    assert especifico.refreshed == 1
    assert legacy.actualizados == 1
    # Con método específico NO se invoca la ruta pesada.
    assert ambos.refreshed == 1 and ambos.actualizados == 0


# ── Test 6: Compras no compara IDs UUID como enteros ─────────────────────────

def test_registrar_compra_uc_accepts_uuid_string_ids():
    from application.use_cases.registrar_compra_uc import (
        RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
    )

    registrado = {}

    class FakePurchaseService:
        def register_purchase(self, **kwargs):
            registrado.update(kwargs)
            return "F-0001", []

    class FakeContainer:
        purchase_service = FakePurchaseService()
        recipe_engine = None

    datos = DatosCompraDTO(
        proveedor_id="01900000-0000-7000-8000-000000000456",
        proveedor_nombre="Proveedor X",
        sucursal_id="01900000-0000-7000-8000-000000000001",
        usuario="tester",
        items=[ItemCompraDTO(
            product_id="01900000-0000-7000-8000-000000000123",
            qty=2.0, unit_cost=10.0, nombre="Producto X")],
        metodo_pago="CONTADO",
        doc_ref="REF-1",
        subtotal=20.0,
        iva_monto=0.0,
        total=20.0,
    )
    # Antes: TypeError «'<=' not supported between instances of 'str' and 'int'»
    resultado = RegistrarCompraUC(FakeContainer()).execute(datos)
    assert resultado.ok, resultado.error
    assert registrado["provider_id"] == datos.proveedor_id
    assert registrado["branch_id"] == datos.sucursal_id

    # Y no quedan comparaciones numéricas sobre IDs en el UC ni en la UI.
    uc_src = _read("application/use_cases/registrar_compra_uc.py")
    assert "proveedor_id <= 0" not in uc_src
    assert "sucursal_id <= 0" not in uc_src
    assert "product_id <= 0" not in uc_src
    # PUR-13: modulos/compras_pro.py eliminado; la aserción sobre su fuente se retiró.


# ── Test 7: la validación de cantidades sigue funcionando ────────────────────

def test_registrar_compra_uc_still_validates_ids_and_quantities():
    from application.use_cases.registrar_compra_uc import (
        RegistrarCompraUC, DatosCompraDTO, ItemCompraDTO,
    )

    class FakeContainer:
        class purchase_service:  # noqa: N801 — stub mínimo
            @staticmethod
            def register_purchase(**kwargs):
                raise AssertionError("no debe llegar a registrar")

    def _datos(**overrides):
        base = dict(
            proveedor_id=new_uuid(), proveedor_nombre="P",
            sucursal_id=new_uuid(), usuario="t",
            items=[ItemCompraDTO(product_id=new_uuid(), qty=1.0,
                                 unit_cost=5.0, nombre="Item")],
            metodo_pago="CONTADO", doc_ref="", subtotal=5.0,
            iva_monto=0.0, total=5.0,
        )
        base.update(overrides)
        return DatosCompraDTO(**base)

    uc = RegistrarCompraUC(FakeContainer())

    # proveedor vacío / "None" → error controlado, no TypeError
    for invalido in ("", "None", "null", "0"):
        r = uc.execute(_datos(proveedor_id=invalido))
        assert not r.ok and "proveedor" in r.error.lower()

    r = uc.execute(_datos(sucursal_id=""))
    assert not r.ok and "sucursal" in r.error.lower()

    # cantidad <= 0 → item inválido reportado por nombre
    r = uc.execute(_datos(items=[ItemCompraDTO(
        product_id=new_uuid(), qty=0, unit_cost=5.0, nombre="SinCantidad")],
        subtotal=0.0, total=0.0))
    assert not r.ok and "SinCantidad" in r.error

    # producto_id vacío → item inválido
    r = uc.execute(_datos(items=[ItemCompraDTO(
        product_id="", qty=1.0, unit_cost=5.0, nombre="SinProducto")]))
    assert not r.ok and "SinProducto" in r.error


# ── Test 8: list_active_branches filtra identidades inválidas ────────────────

def test_list_active_branches_filters_invalid_ids(catalog_db):
    from backend.infrastructure.db.repositories.compras_read_repository import (
        ComprasReadRepository,
    )

    valid_id = new_uuid()
    catalog_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES (?, 'Válida', 1)",
        (valid_id,))
    for bad in (None, "", "None", "null"):
        catalog_db.execute(
            "INSERT INTO sucursales (id, nombre, activa) VALUES (?, ?, 1)",
            (bad, f"Rota-{bad!r}"))
    catalog_db.execute(
        "INSERT INTO sucursales (id, nombre, activa) VALUES (?, 'Inactiva', 0)",
        (new_uuid(),))

    rows = ComprasReadRepository(catalog_db).list_active_branches()
    assert [r["nombre"] for r in rows] == ["Válida"]
    assert rows[0]["id"] == valid_id
