"""§19/§25 — la fuente de recetas de Ventas es PRODUCTOS, no una cadena legacy.

LO QUE HAY HOY (medido, 2026-09-24)
-----------------------------------
- La cadena legacy (`core/services/recipes/recipe_resolver.py`,
  `sales_fulfillment_service.py`, `sales_service.py`) ya no existe y ningún
  código productivo la importa. Seis pruebas viejas todavía la importan y no
  pueden ni cargarse (ver el informe; su baja espera decisión del usuario).
- Ventas usa recetas de Productos en UNA dirección: la reconstrucción inversa
  (parte → base) lee el esquema de corte ACTIVO y reversible de Productos, en
  vivo, para el disponible a prometer y para armar al cobrar.
- La dirección directa (decisión del usuario, 2026-09-24): vender un compuesto
  (receta «Explosión de venta» o combo virtual de Productos) reserva y descuenta
  sus COMPONENTES, que resuelve `SalesFulfillmentQueryService` de Productos. El
  comportamiento completo se prueba en
  `tests/integration/sales/test_sales_composite_explosion.py`.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from backend.application.inventory.queries.sellable_availability_query_service import (
    SellableAvailabilityQueryService,
)
from tests.integration._reversible_cutting import reversible_cutting_scheme
from tests.integration.meat_processing._generic_plant import KG, Planta, build_db

ROOT = Path(__file__).resolve().parents[3]
LEGACY = ("core.services.recipes", "core.services.sales_fulfillment_service",
          "core.services.sales_service", "recipe_resolver")


_IMPORTA = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w, ()]+)|import\s+([\w.]+))",
                     re.M)


def _imports(path: Path) -> set[str]:
    """Módulos y nombres importados (lectura rápida: sólo líneas de import)."""
    modulos = set()
    for de, nombres, directo in _IMPORTA.findall(path.read_text(encoding="utf-8")):
        if directo:
            modulos.add(directo)
        else:
            modulos.add(de)
            modulos |= {f"{de}.{n.strip()}" for n in nombres.strip("() ").split(",") if n.strip()}
    return modulos


def test_no_production_code_uses_the_legacy_recipe_chain():
    fugas = []
    for raiz in ("backend", "frontend"):
        for p in (ROOT / raiz).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if any(m.startswith(LEGACY) or m.endswith("recipe_resolver") for m in _imports(p)):
                fugas.append(p.relative_to(ROOT).as_posix())
    assert fugas == []


def _canal_armable():
    conn = build_db()
    p = Planta(conn)
    especie = p.especie("Porcino")
    canal = p.producto("Canal de cerdo")
    pierna = p.producto("Pierna de cerdo")
    lomo = p.producto("Lomo de cerdo")
    _, version = reversible_cutting_scheme(conn, product_id=canal, reversible=True,
                                           species_id=especie, outputs=[
        {"product_id": pierna, "output_type": "MAIN_PRODUCT", "quantity": "0.6", "unit_id": KG},
        {"product_id": lomo, "output_type": "CO_PRODUCT", "quantity": "0.4", "unit_id": KG}])
    p.existencia(pierna, "6"); p.existencia(lomo, "4")
    return p, canal, version


def test_what_sales_can_promise_comes_from_the_products_cutting_scheme():
    p, canal, version = _canal_armable()
    atp = SellableAvailabilityQueryService(p.conn).get_sellable_availability(
        product_id=canal, branch_id=p.branch, warehouse_id=p.warehouse)
    assert atp.direct == Decimal("0")
    assert atp.reconstructible == Decimal("10")
    assert atp.cutting_scheme_version_id == version


def test_when_products_retires_the_scheme_sales_stops_promising_it():
    """Ventas lee Productos en vivo (no una copia propia): retirar el esquema en
    Productos se refleja de inmediato."""
    p, canal, version = _canal_armable()
    p.conn.execute("UPDATE cutting_scheme_versions SET status='INACTIVE' WHERE id=?",
                   (version,))
    p.conn.commit()
    atp = SellableAvailabilityQueryService(p.conn).get_sellable_availability(
        product_id=canal, branch_id=p.branch, warehouse_id=p.warehouse)
    assert atp.reconstructible == Decimal("0") and atp.cutting_scheme_version_id is None


def test_sales_resolves_composites_through_the_products_contract():
    """Ventas (inventario y costo de venta) no lee recetas ni combos por su
    cuenta: pregunta a Productos."""
    for ruta in ("backend/infrastructure/integrations/sales_inventory_client.py",
                 "backend/application/sales/use_cases/checkout_use_cases.py"):
        importados = _imports(ROOT / ruta)
        assert any(m.endswith("sales_fulfillment_query_service") for m in importados), ruta
        assert not any("repositories.products" in m for m in importados), ruta
