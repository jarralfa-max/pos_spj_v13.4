"""Planta de prueba GENÉRICA para Procesamiento — sin especie ni producto fijo.

Todo lo que distingue un proceso de otro llega como DATOS: qué productos
existen, cuáles se controlan por lote o por calidad, qué despiece o qué receta
tienen, cuánto hay en existencia y a qué costo. Nada aquí sabe qué es una canal
bovina, un lomo porcino, un filete de pescado o una mezcla: los tests los crean
con estos mismos métodos.

Se siembra por los casos de uso REALES de Productos, Inventario y Precios. Los
casos de uso de Procesamiento se autorizan con la política explícita de pruebas;
las integraciones entre contextos NO: usan las concesiones reales.
"""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases.ensure_technical_locations import (
    EnsureTechnicalLocationsUseCase,
    technical_code,
)
from backend.application.inventory.use_cases.lot_use_cases import RegisterInventoryLotUseCase
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.application.meat_processing.authorization import MeatProcessingAuthorizationPolicy
from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.use_cases.order_execution_use_cases import (
    ExecuteProcessingOrderUseCase,
)
from backend.application.meat_processing.use_cases.processing_order_use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.application.meat_processing.use_cases.preparation_use_cases import (
    PrepareProcessingOrderUseCase,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    LotQualityStatus,
    MovementType,
    TechnicalLocationType,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema import meat_processing_schema as mps
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.schema.document_output_schema import (
    create_document_numbering_schema,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.settings_schema import (
    create_company_branch_profile_schema,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.integrations.meat_processing_execution_ports import (
    execution_ports_factory,
    reservation_port_factory,
)
from backend.infrastructure.integrations.meat_processing_ports import (
    ProcessingOrderFolioAdapter,
)
from backend.shared.ids import new_uuid
from tests.integration._reversible_cutting import reversible_cutting_scheme

KG = "unit-kg"


class _Todo:
    def has_permission(self, user_id, code):
        return True


class _Only:
    """Verificador con permisos EXPLÍCITOS por usuario (nada más)."""

    def __init__(self, permisos: dict[str, tuple]) -> None:
        self._permisos = permisos

    def has_permission(self, user_id, code):
        return str(code) in self._permisos.get(str(user_id), ())


def bus_with_real_wiring(conn):
    """Bus con las suscripciones REALES entre contextos: Precios proyecta el
    costo producido, Finanzas asienta la producción y Procesamiento registra la
    decisión de Calidad."""
    from backend.application.costing.wiring import wire_costing
    from backend.application.pricing.integrations.wiring import wire_pricing
    from backend.application.quality.wiring import wire_quality
    from backend.shared.events.application_bus import ApplicationEventBus

    bus = ApplicationEventBus()
    wire_pricing(bus, conn)
    wire_costing(bus, conn)
    wire_quality(bus, conn)
    return bus


def build_db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(c)
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
    create_finance_schema(c)
    bootstrap_finance(c)
    c.execute("CREATE TABLE IF NOT EXISTS sucursales (id TEXT PRIMARY KEY, nombre TEXT NOT NULL,"
              " activa INTEGER DEFAULT 1, fecha_alta DATETIME DEFAULT (datetime('now')))")
    create_company_branch_profile_schema(c)
    create_document_numbering_schema(c)
    for version in ("270_meat_processing_execution",
                    "272_meat_processing_frozen_definition_and_real_reservations",
                    "273_costing_and_quality_contexts",
                    "275_processing_order_folio",
                    "276_meat_processing_production_plan"):
        importlib.import_module(f"migrations.standalone.{version}").run(c)
    c.commit()
    return c


class Planta:
    """Sucursal con un almacén de producción y sus ubicaciones técnicas."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.branch = new_uuid()
        self.warehouse = new_uuid()
        self.operario = new_uuid()
        self.gerente = new_uuid()
        self.inspector = new_uuid()
        conn.execute(
            "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type, status,"
            " allow_sales_allocation, allow_purchase_receipt, allow_production, allow_quarantine,"
            " created_at, updated_at) VALUES (?,?,?,?,'STORE','ACTIVE',1,1,1,1,'x','x')",
            (self.warehouse, f"PLANTA-{self.warehouse[-6:]}", "Planta", self.branch))
        EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id=self.warehouse)
        # La sucursal con su código (Configuración → Empresa): prefijo de folios.
        self.codigo = f"P{self.branch[-4:].upper()}"
        conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?,?)", (self.branch, "Planta"))
        conn.execute("INSERT INTO branch_profiles (id, branch_id, code, name, created_at,"
                     " updated_at) VALUES (?,?,?,?,'x','x')",
                     (self.branch, self.branch, self.codigo, "Planta"))
        self.ubicacion = conn.execute(
            "SELECT id FROM storage_locations WHERE warehouse_id=? AND code=?",
            (self.warehouse, technical_code(TechnicalLocationType.AVAILABLE))).fetchone()[0]
        self._precios = PricingRepository(conn)
        lista = self._precios.active_list_of_kind(PriceListKind.BASE)
        if lista is None:          # varias plantas en una misma base comparten la lista
            lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
            lista.submit(); lista.approve(approved_by_user_id="mgr"); lista.activate()
            self._precios.save_list(lista)
        self._lista = lista.id
        conn.commit()

    # ── maestro (datos, no comportamiento) ──────────────────────────────
    def producto(self, nombre: str, *, lote: bool = False, calidad: bool = False,
                 especie: str | None = None, categoria: str | None = None) -> str:
        pid = new_uuid()
        self.conn.execute(
            "INSERT INTO products (id, code, name, name_normalized, product_type,"
            " lifecycle_status, base_unit_id, lot_controlled, quality_controlled, species_id,"
            " category_id, producible, inventory_managed)"
            " VALUES (?,?,?,?,'RESALE_PRODUCT','ACTIVE',?,?,?,?,?,1,1)",
            (pid, f"P-{pid[-10:]}", nombre, nombre.lower(), KG, int(lote), int(calidad),
             especie, categoria))
        self.conn.commit()
        return pid

    def especie(self, nombre: str) -> str:
        sid = new_uuid()
        self.conn.execute("INSERT INTO species (id, code, name) VALUES (?,?,?)",
                          (sid, f"S-{sid[-8:]}", nombre))
        self.conn.commit()
        return sid

    def costo(self, producto: str, costo: str) -> None:
        self._precios.save_cost(ProductCost(product_id=producto, branch_id=None,
                                            average_cost=Money(Decimal(costo))))
        self.conn.commit()

    def precio(self, producto: str, precio: str) -> None:
        self._precios.save_price(ProductPrice(price_list_id=self._lista, product_id=producto,
                                              sale_price=Money(Decimal(precio))))
        self.conn.commit()

    def despiece(self, fuente: str, salidas: list[tuple[str, str, str]], *,
                 especie: str) -> str:
        """salidas: (producto, tipo, kg de salida por kg de entrada)."""
        _, version = reversible_cutting_scheme(self.conn, product_id=fuente, reversible=False,
                                               species_id=especie, outputs=[
            {"product_id": p, "output_type": t, "quantity": q, "unit_id": KG}
            for p, t, q in salidas])
        return version

    def receta(self, producto: str, componentes: list[tuple[str, str]],
               salidas: list[tuple[str, str, str]] | None = None,
               tipo: str = "FORMULA") -> str:
        """componentes: (insumo, cantidad); salidas: (producto, tipo, cantidad)."""
        auth = ProductsAuthorizationPolicy(_Todo())
        r = CreateProductRecipeUseCase(self.conn, auth).execute(CreateRecipeCommand(
            operation_id=new_uuid(), product_id=producto, recipe_type=tipo, name="Receta",
            components=[{"component_product_id": p, "quantity": q, "unit_id": KG}
                        for p, q in componentes],
            outputs=[{"product_id": p, "output_type": t, "quantity": q, "unit_id": KG}
                     for p, t, q in (salidas or [])],
            user_id="alice"))
        assert r.success, r.message
        for caso, quien in ((SubmitRecipeVersionUseCase, "alice"),
                            (ApproveRecipeVersionUseCase, "bob"),
                            (ActivateRecipeVersionUseCase, "bob")):
            t = caso(self.conn, auth).execute(RecipeVersionTransitionCommand(
                operation_id=new_uuid(), version_id=r.version_id, user_id=quien))
            assert t.success, t.message
        return r.version_id

    # ── existencia real, por Inventario ─────────────────────────────────
    def existencia(self, producto: str, kg: str, *, lote: str | None = None,
                   vence: str | None = None) -> str | None:
        """Recepción de compra en la ubicación técnica del almacén, con lote si se
        pide. Devuelve el id del lote (o None)."""
        auth = InventoryAuthorizationPolicy.permissive_for_tests()
        lot_id = None
        if lote:
            r = RegisterInventoryLotUseCase(auth).execute(
                self.conn, product_id=producto, lot_code=lote, origin_type=LotOrigin.PURCHASE,
                operation_id=new_uuid(), actor_user_id=self.gerente, branch_id=self.branch,
                expiration_date=vence, quality_status=LotQualityStatus.RELEASED)
            assert r.success, r.message
            lot_id = r.entity_id
        movimiento = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id=self.branch,
            warehouse_id=self.warehouse, source_module="procurement",
            source_document_type="PURCHASE", source_document_id=new_uuid(),
            operation_id=new_uuid(), created_by_user_id=self.gerente,
            lines=[InventoryMovementLine.create(
                product_id=producto, quantity=Decimal(kg), lot_id=lot_id,
                to_location_id=self.ubicacion, to_status=InventoryStatus.AVAILABLE,
                reason_code="PURCHASE")])
        r = PostInventoryMovementUseCase(auth).execute(self.conn, movimiento,
                                                       actor_user_id=self.gerente)
        assert r.success, r.message
        return lot_id

    def saldo(self, producto: str, estado: str = "AVAILABLE") -> Decimal:
        fila = self.conn.execute(
            "SELECT quantity FROM inventory_balances WHERE product_id=? AND inventory_status=?",
            (producto, estado)).fetchall()
        return sum((Decimal(str(f[0])) for f in fila), Decimal("0"))

    def reservado(self, producto: str) -> Decimal:
        fila = self.conn.execute(
            "SELECT reserved_quantity FROM inventory_balances WHERE product_id=?",
            (producto,)).fetchall()
        return sum((Decimal(str(f[0] or 0)) for f in fila), Decimal("0"))

    # ── ciclo de la orden ────────────────────────────────────────────────
    def auth(self):
        return MeatProcessingAuthorizationPolicy.permissive_for_tests()

    def orden(self, proceso: ProcessType, objetivo: str, peso: str) -> str:
        r = CreateProcessingOrderUseCase(
            self.auth(), folio_port=ProcessingOrderFolioAdapter).execute(
            self.conn, operation_id=new_uuid(), branch_id=self.branch,
            warehouse_id=self.warehouse, process_type=proceso, target_product_id=objetivo,
            planned_quantity=Decimal("0"), planned_weight=Decimal(peso),
            actor_user_id=self.operario)
        assert r.success, r.message
        assert ApproveProcessingOrderUseCase(self.auth()).execute(
            self.conn, order_id=r.entity_id, operation_id=new_uuid(),
            actor_user_id=self.gerente).success
        return r.entity_id

    def preparar(self, oid: str):
        return PrepareProcessingOrderUseCase(
            self.auth(), recipe_snapshot_port=ProductsRecipeSnapshotAdapter(self.conn),
            reservation_port_factory=reservation_port_factory(self.conn)).execute(
            self.conn, order_id=oid, operation_id=new_uuid(), actor_user_id=self.operario)

    def liberar(self, oid: str):
        return ReleaseProcessingOrderUseCase(self.auth()).execute(
            self.conn, order_id=oid, operation_id=new_uuid(), actor_user_id=self.operario)

    def lista(self, proceso: ProcessType, objetivo: str, peso: str) -> str:
        oid = self.orden(proceso, objetivo, peso)
        r = self.preparar(oid)
        assert r.success and r.data.get("ready"), (r.message, r.data)
        r = self.liberar(oid)
        assert r.success, r.message
        return oid

    def decidir_calidad(self, output_id: str, decision: str, *, quien: str | None = None,
                        motivo: str = "", dispatch=None):
        """Calidad decide sobre un output (con su propia política: sólo el
        inspector tiene el permiso de decidir)."""
        from backend.application.quality.output_inspection import (
            DecideOutputInspectionUseCase,
            QualityAuthorizationPolicy,
        )
        from backend.application.quality.permissions import QualityPermissions
        from backend.infrastructure.db.repositories.quality.inspection_repository import (
            InspectionRepository,
        )

        inspeccion = InspectionRepository(self.conn).find_by_subject("PROCESS_OUTPUT", output_id)
        assert inspeccion is not None, "no hay inspección pedida para ese output"
        politica = QualityAuthorizationPolicy(_Only({
            self.inspector: (QualityPermissions.INSPECTION_DECIDE,
                             QualityPermissions.INSPECTION_VIEW)}))
        return DecideOutputInspectionUseCase(politica).execute(
            self.conn, inspection_id=inspeccion.id, decision=decision, reason=motivo,
            operation_id=new_uuid(), actor_user_id=quien or self.inspector, dispatch=dispatch)

    def salida(self, oid: str, producto: str):
        from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
            MeatProcessingUnitOfWork,
        )
        return next(s for s in MeatProcessingUnitOfWork(self.conn).outputs.list_by_order(oid)
                    if s.product_id == producto)

    def ejecutar(self, oid: str, salidas: dict[str, str], *, entradas=None,
                 dispatch=None, **extra):
        uc = ExecuteProcessingOrderUseCase(
            self.auth(), ports_factory=execution_ports_factory(dispatch_costing=dispatch),
            authorizer_checker=_Todo())
        return uc.execute(
            self.conn, order_id=oid, actor_user_id=self.operario, operation_id=new_uuid(),
            outputs=[{"product_id": p, "weight": Decimal(k)} for p, k in salidas.items()],
            inputs=(None if entradas is None else
                    [{"product_id": p, "weight": Decimal(k)} for p, k in entradas.items()]),
            **extra)


def released_order(conn, *, peso: str = "100") -> tuple[Planta, str, str]:
    """Una orden REALMENTE preparada (definición congelada, insumo reservado en
    Inventario) y liberada. Para pruebas cuyo tema es lo que viene después
    (arrancar, pausar, incidentes, cerrar), no la preparación. Devuelve
    (planta, id de la orden, id del insumo)."""
    p = Planta(conn)
    familia = p.especie("Especie de prueba")
    fuente = p.producto("Insumo", especie=familia)
    salida = p.producto("Salida", especie=familia)
    merma = p.producto("Merma", especie=familia)
    p.despiece(fuente, [(salida, "MAIN_PRODUCT", "0.80"), (merma, "WASTE", "0.20")],
               especie=familia)
    p.existencia(fuente, str(Decimal(peso) * 2))
    return p, p.lista(ProcessType.DISASSEMBLY, fuente, peso), fuente

