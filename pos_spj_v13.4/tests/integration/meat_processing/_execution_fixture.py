"""Base de prueba para ejecutar órdenes de despiece por los casos de uso REALES.

Esquemas reales (Mermas 174, Productos, Precios + 151, Inventario, Cárnico +
270). Pollo entero con existencia y costo; despiece por kg (0.35 pechuga,
0.30 pierna, 0.12 ala, 0.05 merma) con precios de venta 120/80/60.
"""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.use_cases.processing_order_use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema import meat_processing_schema as mps
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from tests.integration._pos_ready import stock_product
from tests.integration._reversible_cutting import reversible_cutting_scheme

KG = "unit-kg"


def build_db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(c)
    # La 174 activa las llaves foráneas; esta base siembra productos por id sin
    # su maestro. La integridad real se verifica sobre la copia de la base real.
    c.execute("PRAGMA foreign_keys=OFF")
    create_products_schema(c)
    create_pricing_schema(c)
    importlib.import_module("migrations.standalone.151_pricing_cost_tracked_quantity").run(c)
    create_inventory_schema(c)
    for fn in ("create_meat_processing_schema", "create_meat_processing_preparation_execution_schema",
               "create_meat_processing_packaging_schema", "create_meat_processing_rework_schema",
               "create_meat_processing_genealogy_schema", "create_meat_processing_resources_schema"):
        getattr(mps, fn)(c)
    c.execute("CREATE TABLE IF NOT EXISTS configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    importlib.import_module("migrations.standalone.270_meat_processing_execution").run(c)
    c.commit()
    return c


class Planta:
    """Sucursal con almacén de producción, pollo en existencia y su despiece."""

    def __init__(self, conn, *, pollo_kg="10", costo_pollo="50", precios=None):
        self.conn = conn
        self.branch = new_uuid()
        self.warehouse = new_uuid()
        conn.execute(
            "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type, status,"
            " allow_sales_allocation, allow_purchase_receipt, allow_production, allow_quarantine,"
            " created_at, updated_at) VALUES (?,?,?,?,'STORE','ACTIVE',1,1,1,0,'x','x')",
            (self.warehouse, "PLANTA", "Planta", self.branch))
        self.pollo, self.pechuga, self.pierna, self.ala, self.merma = (new_uuid() for _ in range(5))
        reversible_cutting_scheme(conn, product_id=self.pollo, reversible=False, outputs=[
            {"product_id": self.pechuga, "output_type": "MAIN_PRODUCT", "quantity": "0.35", "unit_id": KG},
            {"product_id": self.pierna, "output_type": "CO_PRODUCT", "quantity": "0.30", "unit_id": KG},
            {"product_id": self.ala, "output_type": "CO_PRODUCT", "quantity": "0.12", "unit_id": KG},
            {"product_id": self.merma, "output_type": "WASTE", "quantity": "0.05", "unit_id": KG}])
        if pollo_kg:
            stock_product(conn, product_id=self.pollo, branch_id=self.branch, quantity=pollo_kg,
                          warehouse_id=self.warehouse)
        repo = PricingRepository(conn)
        if costo_pollo:
            repo.save_cost(ProductCost(product_id=self.pollo, branch_id=None,
                                       average_cost=Money(Decimal(costo_pollo))))
        lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
        lista.submit(); lista.approve(approved_by_user_id="mgr"); lista.activate()
        repo.save_list(lista)
        for pid, precio in (precios or {self.pechuga: "120", self.pierna: "80",
                                         self.ala: "60"}).items():
            repo.save_price(ProductPrice(price_list_id=lista.id, product_id=pid,
                                         sale_price=Money(Decimal(precio))))
        conn.commit()

    def orden_liberada(self, *, peso="10", creador=None, aprobador=None) -> str:
        auth = MeatProcessingAuthorizationPolicy.permissive_for_tests()
        creador, aprobador = creador or new_uuid(), aprobador or new_uuid()
        r = CreateProcessingOrderUseCase(auth).execute(
            self.conn, operation_id=new_uuid(), branch_id=self.branch,
            warehouse_id=self.warehouse, process_type=ProcessType.DISASSEMBLY,
            target_product_id=self.pollo, planned_quantity=Decimal("0"),
            planned_weight=Decimal(peso), actor_user_id=creador)
        assert r.success, r.message
        assert ApproveProcessingOrderUseCase(auth).execute(
            self.conn, order_id=r.entity_id, operation_id=new_uuid(), actor_user_id=aprobador).success
        assert ReleaseProcessingOrderUseCase(
            auth, recipe_snapshot_port=ProductsRecipeSnapshotAdapter(self.conn)).execute(
            self.conn, order_id=r.entity_id, operation_id=new_uuid(), actor_user_id=creador).success
        return r.entity_id

    def saldo(self, producto) -> Decimal:
        fila = self.conn.execute("SELECT SUM(CAST(quantity AS REAL)) FROM inventory_balances"
                                 " WHERE product_id=?", (producto,)).fetchone()[0]
        return Decimal(str(fila or 0)).quantize(Decimal("0.001"))
