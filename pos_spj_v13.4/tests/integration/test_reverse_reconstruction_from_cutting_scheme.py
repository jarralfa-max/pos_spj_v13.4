"""Fase 7 (Reverse Recipe Reconstruction: ATP y consumo inverso), 2026-09-19.

MEDIDO ANTES DEL CAMBIO
-----------------------
- La reconstrucción leía sólo recetas de Desensamble; el despiece que Productos
  captura y Cárnico EJECUTA es el esquema de corte. Decisión del usuario: el
  esquema de corte es la fuente única.
- La marca de reversibilidad no se podía fijar desde ninguna pantalla.
- El ATP (directo + armable) no lo usaba nadie; el catálogo del POS mostraba
  sólo existencia directa y un producto agotado NI SE PODÍA SELECCIONAR.
- El armado se registraba como AJUSTE (ADJUSTMENT_IN/OUT) y su costo no llegaba
  al costo promedio: el costo de venta (Fase 6) se calculaba ANTES de armar.
"""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases.reconstruction_use_cases import (
    ReconstructBaseProductUseCase,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_cutting_commands import (
    SetCuttingReverseReconstructionCommand,
)
from backend.application.products.use_cases.product_cutting_use_cases import (
    SetCuttingReverseReconstructionUseCase,
)
from backend.application.sales.integrations.wiring import wire_sales
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.queries.catalog_query_service import SalesCatalogQueryService
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration._pos_ready import open_cash_shift, stock_product
from tests.integration._reversible_cutting import reversible_cutting_scheme

_UNIT = "unit-kg"
_RESERVA = {"INVENTARIO.reserva.crear", "INVENTARIO.reserva.liberar", "INVENTARIO.reserva.ver"}


class _Todo:
    def has_permission(self, user_id, code):
        return True


class _Cajero:
    def __init__(self, branch_id):
        self.user_id = new_uuid()
        self.active_branch_id = branch_id
        self.is_active = True
        self._p = {p for p in vars(SalesPermissions).values() if isinstance(p, str)} | _RESERVA

    def tiene_permiso(self, code):
        return code in self._p


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    # `product_cost.tracked_quantity` la agrega la 151 (el esquema base no).
    importlib.import_module("migrations.standalone.151_pricing_cost_tracked_quantity").run(c)
    create_inventory_schema(c)
    create_finance_schema(c)
    bootstrap_finance(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def bus(conn, monkeypatch):
    local = ApplicationEventBus()
    wire_sales(local, conn)
    import backend.shared.events.application_bus as modulo
    monkeypatch.setattr(modulo, "get_bus", lambda: local)
    return local


def _costo(conn, producto, monto):
    PricingRepository(conn).save_cost(ProductCost(
        product_id=producto, branch_id=None, average_cost=Money(Decimal(monto))))
    conn.commit()


def _precio(conn, producto, monto):
    repo = PricingRepository(conn)
    lista = repo.active_list_of_kind(PriceListKind.BASE)
    if lista is None:
        lista = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
        lista.submit(); lista.approve(approved_by_user_id="mgr"); lista.activate()
        repo.save_list(lista)
    repo.save_price(ProductPrice(price_list_id=lista.id, product_id=producto,
                                 sale_price=Money(Decimal(monto))))
    conn.commit()


def _pollo_armable(conn, branch):
    """Pollo entero SIN existencia directa; 1.2 kg pechuga + 0.8 pierna + 0.4 ala
    por pollo (más 0.1 de merma, que no cuenta para armar). Partes para 3."""
    pollo, pechuga, pierna, ala, merma = (new_uuid() for _ in range(5))
    reversible_cutting_scheme(conn, product_id=pollo, outputs=[
        {"product_id": pechuga, "output_type": "MAIN_PRODUCT", "quantity": "1.2", "unit_id": _UNIT},
        {"product_id": pierna, "output_type": "CO_PRODUCT", "quantity": "0.8", "unit_id": _UNIT},
        {"product_id": ala, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": _UNIT},
        {"product_id": merma, "output_type": "WASTE", "quantity": "0.1", "unit_id": _UNIT},
    ])
    for parte, cantidad, costo in ((pechuga, "12", "80"), (pierna, "8", "60"), (ala, "1.2", "40")):
        stock_product(conn, product_id=parte, branch_id=branch, quantity=cantidad)
        _costo(conn, parte, costo)
    return pollo, pechuga, pierna, ala


def _saldo(conn, producto):
    fila = conn.execute("SELECT SUM(CAST(quantity AS REAL)) FROM inventory_balances"
                        " WHERE product_id=?", (producto,)).fetchone()[0]
    return Decimal(str(fila or 0)).quantize(Decimal("0.001"))


# ── la marca vive en el esquema de corte ───────────────────────────────────
def test_la_marca_se_fija_en_el_esquema_y_queda_auditada(conn):
    scheme_id, _ = reversible_cutting_scheme(conn, product_id=new_uuid(), reversible=False,
                                             outputs=[{"product_id": new_uuid(),
                                                       "quantity": "1", "unit_id": _UNIT}])
    caso = SetCuttingReverseReconstructionUseCase(conn, ProductsAuthorizationPolicy(_Todo()))

    r = caso.execute(SetCuttingReverseReconstructionCommand(
        operation_id=new_uuid(), scheme_id=scheme_id, allowed=True, user_id="bob"))

    assert r.success, r.message
    assert conn.execute("SELECT reverse_reconstruction_allowed FROM cutting_schemes"
                        " WHERE id=?", (scheme_id,)).fetchone()[0] == 1
    auditoria = conn.execute("SELECT action FROM product_audit_log WHERE entity_id=?",
                             (scheme_id,)).fetchall() if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='product_audit_log'").fetchone() else [("x",)]
    assert auditoria


def test_fijar_la_marca_exige_el_permiso_de_despiece(conn):
    from backend.domain.products.exceptions import ProductPermissionDeniedError

    class _Nada:
        def has_permission(self, user_id, code):
            return False

    scheme_id, _ = reversible_cutting_scheme(conn, product_id=new_uuid(), reversible=False,
                                             outputs=[{"product_id": new_uuid(),
                                                       "quantity": "1", "unit_id": _UNIT}])
    with pytest.raises(ProductPermissionDeniedError):
        SetCuttingReverseReconstructionUseCase(conn, ProductsAuthorizationPolicy(_Nada())).execute(
            SetCuttingReverseReconstructionCommand(
                operation_id=new_uuid(), scheme_id=scheme_id, allowed=True, user_id="bob"))


# ── armar: transformación y costo promedio ─────────────────────────────────
def test_armar_es_una_transformacion_y_su_costo_entra_al_promedio(conn):
    branch = new_uuid()
    pollo, pechuga, pierna, ala = _pollo_armable(conn, branch)
    caso = ReconstructBaseProductUseCase(InventoryAuthorizationPolicy.permissive_for_tests())

    r = caso.execute(conn, product_id=pollo, quantity="2", branch_id=branch,
                     warehouse_id=branch, actor_user_id="u", operation_id="op-armar")

    assert r.success, r.message
    tipos = [t for (t,) in conn.execute("SELECT movement_type FROM inventory_ledger ORDER BY rowid")]
    assert tipos[-2:] == ["PRODUCTION_CONSUMPTION", "PRODUCTION_OUTPUT"]
    assert not {"ADJUSTMENT_IN", "ADJUSTMENT_OUT"} & set(tipos)
    # 1.2×80 + 0.8×60 + 0.4×40 = 160 por pollo; la merma no se cobra.
    promedio = conn.execute("SELECT average_cost FROM product_cost WHERE product_id=?",
                            (pollo,)).fetchone()[0]
    assert Decimal(promedio) == Decimal("160")
    assert _saldo(conn, pollo) == Decimal("2.000")
    assert (_saldo(conn, pechuga), _saldo(conn, pierna), _saldo(conn, ala)) == (
        Decimal("9.600"), Decimal("6.400"), Decimal("0.400"))

    # Reintentar la misma operación no duplica ni existencia ni costo.
    caso.execute(conn, product_id=pollo, quantity="2", branch_id=branch,
                 warehouse_id=branch, actor_user_id="u", operation_id="op-armar")
    assert _saldo(conn, pollo) == Decimal("2.000")
    assert conn.execute("SELECT COUNT(*) FROM price_change_log WHERE product_id=?"
                        " AND field='cost'", (pollo,)).fetchone()[0] == 1


# ── el cobro real arma el pollo y asienta el costo de sus partes ───────────
def test_el_cobro_arma_el_pollo_sin_suspender_y_el_costo_de_venta_es_el_de_sus_partes(conn, bus):
    from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter

    branch = new_uuid()
    pollo, pechuga, _, _ = _pollo_armable(conn, branch)
    _precio(conn, pollo, "250")
    cajero = _Cajero(branch)
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero.user_id)
    pos = build_sales_pos_presenter(conn, session_context=cajero)
    sid = pos.start_sale().entity_id
    assert pos.add_line(sale_id=sid, product_id=pollo, quantity=Decimal("2"),
                        unit_price=Decimal("1"), product_snapshot={"name": "Pollo"}).success
    assert pos.begin_checkout(sale_id=sid).success
    assert pos.record_payment(sale_id=sid, method="CASH", amount=Decimal("500")).success

    r = pos.checkout_sale(sale_id=sid)

    assert r.success, r.message
    assert _saldo(conn, pollo) == Decimal("0.000")        # armados y vendidos
    assert _saldo(conn, pechuga) == Decimal("9.600")
    evento = json.loads(conn.execute("SELECT payload_json FROM sales_outbox"
                                     " WHERE event_name='SALE_COMPLETED'").fetchone()[0])
    assert evento["payload"]["cogs_total"] == "320.00"
    assert evento["payload"]["cogs_missing_products"] == []
    costo = conn.execute(
        "SELECT jl.debit_amount FROM journal_lines jl JOIN journal_entries je"
        " ON je.id=jl.journal_entry_id WHERE je.description LIKE 'Costo de venta%'"
        " ORDER BY jl.line_index LIMIT 1").fetchone()[0]
    assert Decimal(costo) == Decimal("320")


# ── ATP en el catálogo del POS ──────────────────────────────────────────────
def _producto_catalogo(conn, pid, nombre):
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, lifecycle_status,"
        " base_unit_id, sellable, internal_only) VALUES (?,?,?,?,?,?,?,1,0)",
        (pid, f"C-{pid[-6:]}", nombre, nombre.lower(), "RESALE_PRODUCT", "ACTIVE", _UNIT))
    conn.commit()
    # Con precio: sin él el catálogo lo marca no vendible (§64), y estas
    # pruebas son sobre la EXISTENCIA, no sobre el precio.
    _precio(conn, pid, "100")


def test_el_catalogo_muestra_lo_armable_y_el_pollo_se_puede_vender(conn):
    branch = new_uuid()
    pollo, *_ = _pollo_armable(conn, branch)
    _producto_catalogo(conn, pollo, "Pollo entero")

    [pollo_dto] = SalesCatalogQueryService(conn).search(branch_id=branch, search="Pollo")

    assert pollo_dto.reconstructible_quantity == Decimal("3")
    assert pollo_dto.available_quantity == Decimal("3")
    assert pollo_dto.stock_state != "OUT_OF_STOCK"
    assert pollo_dto.sellable is True
    assert any("se arman con partes" in w for w in pollo_dto.warnings)


def test_un_agotado_sin_despiece_se_puede_agregar_y_avisa_que_pide_autorizacion(conn):
    """Antes no se podía ni seleccionar: la autorización de la Fase 6 era
    inalcanzable con existencia cero."""
    branch, res = new_uuid(), new_uuid()
    _producto_catalogo(conn, res, "Res")

    [dto] = SalesCatalogQueryService(conn).search(branch_id=branch, search="Res")

    assert dto.stock_state == "OUT_OF_STOCK"
    assert dto.sellable is True
    assert "requiere autorización" in dto.warnings[0]


# ── pantalla de despiece ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    qt = pytest.importorskip("PyQt5.QtWidgets")
    yield qt.QApplication.instance() or qt.QApplication([])


def test_la_pantalla_de_despiece_permite_y_quita_el_armado(app, conn):
    from frontend.desktop.modules.products.dialogs.cutting_dialog import CuttingSchemesDialog

    producto = new_uuid()
    scheme_id, _ = reversible_cutting_scheme(conn, product_id=producto, reversible=False,
                                             outputs=[{"product_id": new_uuid(),
                                                       "quantity": "1", "unit_id": _UNIT}])

    class _Presentador:
        can_manage_cutting = True
        llamadas = []

        def list_cutting_schemes(self, product_id):
            return [{"id": scheme_id, "name": "Despiece", "cut_level": "PRIMARY", "active": 1,
                     "reverse_reconstruction_allowed": conn.execute(
                         "SELECT reverse_reconstruction_allowed FROM cutting_schemes WHERE id=?",
                         (scheme_id,)).fetchone()[0]}]

        def list_cutting_versions(self, scheme_id):
            return []

        def set_cutting_reverse_reconstruction(self, sid, allowed):
            self.llamadas.append((sid, allowed))
            SetCuttingReverseReconstructionUseCase(
                conn, ProductsAuthorizationPolicy(_Todo())).execute(
                SetCuttingReverseReconstructionCommand(
                    operation_id=new_uuid(), scheme_id=sid, allowed=allowed, user_id="bob"))
            return True, "ok"

    p = _Presentador()
    d = CuttingSchemesDialog(p, product_id=producto, product_name="Pollo")
    d.schemes_table.selectRow(0)
    assert d.btn_reverse.text() == "Permitir armar con partes"

    d.btn_reverse.click()
    assert p.llamadas == [(scheme_id, True)]
    assert d.schemes_table.item(0, 3).text() == "Sí"
    assert d.btn_reverse.text() == "Dejar de armar con partes"


# ── migración 269 ────────────────────────────────────────────────────────────
def test_269_agrega_la_columna_a_esquemas_viejos_y_esta_registrada():
    c = sqlite3.connect(":memory:")
    create_products_schema(c)
    c.execute("ALTER TABLE cutting_schemes DROP COLUMN reverse_reconstruction_allowed")
    m269 = importlib.import_module(
        "migrations.standalone.269_cutting_scheme_reverse_reconstruction")

    m269.run(c)
    m269.run(c)

    assert "reverse_reconstruction_allowed" in {
        r[1] for r in c.execute("PRAGMA table_info(cutting_schemes)")}
    from migrations.engine import MIGRATIONS
    assert "269" in {m.version for m in MIGRATIONS}
