"""`RecipeSnapshotPort` real: resuelve en Productos la definición productiva
COMPLETA de una orden y la entrega como `ProcessingRecipeSnapshot`.

Productos define; Procesamiento ejecuta. Este adaptador es el único punto
donde Procesamiento lee recetas, esquemas de corte y perfiles de rendimiento,
y sólo lo hace al congelar la definición de una orden (o al rellenar la de una
orden ya liberada, con las versiones que capturó). La ejecución NUNCA pasa por
aquí: lee la foto congelada.

Qué se lee según la familia del proceso (nunca según la especie):

- DISASSEMBLY: esquema de corte y perfil de rendimiento de la ENTRADA
  (`target_product_id`). Cada salida del esquema trae su factor (kg de salida
  por kg de entrada); el perfil, si existe, añade % esperado/mínimo/máximo.
- FORMULATION: receta de producción del producto a FABRICAR
  (`target_product_id`): componentes y salidas. Una receta de venta
  (`SALES_EXPLOSION`) es de Ventas y aquí no cuenta.
- PACKAGING: la receta de empaque (`PACKAGING_BOM`) del producto, o su
  presentación en el perfil logístico (peso neto).
- CONDITIONING: el mismo producto entra y sale; el perfil de rendimiento, si
  existe, dice cuánto se espera conservar.

Conservador por diseño: una definición cuenta sólo si hay EXACTAMENTE una
versión ACTIVA. Cero es "no aplica"; más de una es un estado que se niega a
adivinar. Las banderas de lote y de calidad de cada producto se congelan con
la foto, para que la ejecución no tenga que volver a Productos.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.products.queries.integration_query_services import (
    InventoryProductConfigQueryService,
    ProcessingProductConfigQueryService,
    QualityProductConfigQueryService,
)
from backend.application.products.queries.product_cutting_query_service import (
    ProductCuttingQueryService,
)
from backend.application.products.queries.product_recipe_query_service import (
    ProductRecipeQueryService,
)
from backend.application.products.queries.product_yield_query_service import (
    ProductYieldQueryService,
)
from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    InputRole,
    ProcessFamily,
    ProcessingRecipeSnapshot,
    SnapshotInput,
    SnapshotOutput,
    process_family,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.domain.products.recipe_enums import RecipeType, RecipeVersionStatus
from backend.infrastructure.db.repositories.products.profile_repository import ProfileRepository

logger = logging.getLogger("spj.meat_processing.products_recipe_snapshot")

_ACTIVE = RecipeVersionStatus.ACTIVE.value
_HUNDRED = Decimal("100")

#: Recetas que describen una transformación productiva de varias entradas.
FORMULATION_RECIPE_TYPES = frozenset({
    RecipeType.PRODUCTION_BOM.value, RecipeType.PROCESSING_RECIPE.value,
    RecipeType.FORMULA.value, RecipeType.MARINATION.value, RecipeType.GRINDING.value,
    RecipeType.MIXING.value,
})
PACKAGING_RECIPE_TYPES = frozenset({RecipeType.PACKAGING_BOM.value})


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _single_active_version(*, label: str, product_id: str, rows, list_versions,
                           version_detail) -> dict | None:
    candidates: list[dict] = []
    for row in rows:
        if not row.get("active"):
            continue
        for version in list_versions(row["id"]):
            if version.get("status") == _ACTIVE:
                candidates.append(version)
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning("%s: %d versiones ACTIVAS para %s; no se adivina cuál aplica",
                       label, len(candidates), product_id)
        return None
    return version_detail(candidates[0]["id"])


class ProductsRecipeSnapshotAdapter:
    """Implementa `RecipeSnapshotPort` contra los catálogos reales de Productos."""

    def __init__(self, connection) -> None:
        self._recipes = ProductRecipeQueryService(connection)
        self._yields = ProductYieldQueryService(connection)
        self._cutting = ProductCuttingQueryService(connection)
        self._inventory_config = InventoryProductConfigQueryService(connection)
        self._quality_config = QualityProductConfigQueryService(connection)
        self._classification = ProcessingProductConfigQueryService(connection)
        self._profiles = ProfileRepository(connection)

    # ── contrato ────────────────────────────────────────────────────────
    def resolve(self, *, target_product_id: str,
                process_type: ProcessType) -> ProcessingRecipeSnapshot | None:
        """La definición ACTIVA hoy en Productos para ese proceso y producto."""
        familia = process_family(process_type)
        if familia is None:
            return None
        recipe = scheme = yield_profile = packaging_recipe = None
        if familia is ProcessFamily.DISASSEMBLY:
            scheme = self._active_cutting(target_product_id)
            yield_profile = self._active_yield(target_product_id)
        elif familia is ProcessFamily.FORMULATION:
            recipe = self._active_recipe(target_product_id, FORMULATION_RECIPE_TYPES)
            yield_profile = self._active_yield(target_product_id)
        elif familia is ProcessFamily.PACKAGING:
            packaging_recipe = self._active_recipe(target_product_id, PACKAGING_RECIPE_TYPES)
        else:
            yield_profile = self._active_yield(target_product_id)
        return self._build(process_type, target_product_id, familia, recipe=recipe,
                           scheme=scheme, yield_profile=yield_profile,
                           packaging_recipe=packaging_recipe)

    def from_versions(self, *, target_product_id: str, process_type: ProcessType,
                      recipe_version_id: str | None, cutting_scheme_version_id: str | None,
                      yield_profile_version_id: str | None) -> ProcessingRecipeSnapshot | None:
        """La definición de unas versiones YA capturadas (órdenes liberadas antes
        de que existiera la foto). Las versiones activas o superadas de Productos
        son inmutables, así que reconstruirlas es fiel."""
        familia = process_family(process_type)
        if familia is None:
            return None
        recipe = (self._recipes.version_detail(recipe_version_id)
                  if recipe_version_id else None)
        return self._build(
            process_type, target_product_id, familia,
            recipe=recipe if familia is ProcessFamily.FORMULATION else None,
            scheme=(self._cutting.version_detail(cutting_scheme_version_id)
                    if cutting_scheme_version_id else None),
            yield_profile=(self._yields.version_detail(yield_profile_version_id)
                           if yield_profile_version_id else None),
            packaging_recipe=recipe if familia is ProcessFamily.PACKAGING else None)

    # ── lectura de catálogos ────────────────────────────────────────────
    def _active_cutting(self, product_id):
        return _single_active_version(
            label="cutting_scheme", product_id=product_id,
            rows=self._cutting.list_schemes(product_id),
            list_versions=self._cutting.list_versions,
            version_detail=self._cutting.version_detail)

    def _active_yield(self, product_id):
        return _single_active_version(
            label="yield_profile", product_id=product_id,
            rows=self._yields.list_profiles(product_id),
            list_versions=self._yields.list_versions,
            version_detail=self._yields.version_detail)

    def _active_recipe(self, product_id, types):
        return _single_active_version(
            label="recipe", product_id=product_id,
            rows=[r for r in self._recipes.list_recipes(product_id)
                  if r.get("recipe_type") in types],
            list_versions=self._recipes.list_versions,
            version_detail=self._recipes.version_detail)

    def _flags(self, product_id: str) -> tuple[bool, bool]:
        """(lote obligatorio, compuerta de calidad) según Productos."""
        inventario = self._inventory_config.get(product_id)
        calidad = self._quality_config.get(product_id)
        lote = bool(inventario and (inventario.lot_controlled or inventario.traceability_required))
        compuerta = bool((inventario and inventario.quality_controlled)
                         or (calidad and (calidad.inspection_required
                                          or calidad.quarantine_required)))
        return lote, compuerta

    # ── construcción ────────────────────────────────────────────────────
    def _build(self, process_type, target, familia, *, recipe, scheme, yield_profile,
               packaging_recipe) -> ProcessingRecipeSnapshot | None:
        rendimiento = {o["product_id"]: o for o in (yield_profile or {}).get("outputs", [])}
        entradas: list[SnapshotInput] = []
        salidas: list[SnapshotOutput] = []
        base = Decimal("1")
        packaging_spec: dict = {}

        def salida(pid, tipo, factor, *, medida="BY_WEIGHT", unidad=None, orden=0, origen=""):
            perfil = rendimiento.get(pid, {})
            lote, compuerta = self._flags(pid)
            esperado = _dec(perfil.get("expected_yield_pct"))
            return SnapshotOutput(
                product_id=pid, output_type=tipo, expected_factor=factor,
                measure_kind=medida, expected_yield_pct=esperado,
                minimum_yield_pct=_dec(perfil.get("minimum_yield_pct")),
                maximum_yield_pct=_dec(perfil.get("maximum_yield_pct")),
                unit_id=unidad or perfil.get("unit_id"), sequence=orden,
                lot_controlled=lote, quality_gate=compuerta, source=origen)

        def fuente():
            lote, _ = self._flags(target)
            return SnapshotInput(product_id=target, role=InputRole.SOURCE,
                                 quantity_per_basis=Decimal("1"), lot_controlled=lote)

        if familia is ProcessFamily.DISASSEMBLY:
            if scheme is None and not rendimiento:
                return self._empty(process_type, target, yield_profile)
            entradas.append(fuente())
            for o in (scheme or {}).get("outputs", []):
                salidas.append(salida(
                    o["product_id"], o["output_type"], Decimal(str(o["quantity"])),
                    medida=o.get("measure_kind") or "BY_WEIGHT", unidad=o.get("unit_id"),
                    orden=o.get("sequence") or 0, origen="CUTTING_SCHEME"))
            if scheme is None:
                for o in rendimiento.values():
                    salidas.append(salida(
                        o["product_id"], o["output_type"],
                        (_dec(o.get("expected_yield_pct")) or Decimal("0")) / _HUNDRED,
                        unidad=o.get("unit_id"), orden=o.get("sequence") or 0,
                        origen="YIELD_PROFILE"))
        elif familia is ProcessFamily.FORMULATION:
            if recipe is None:
                return self._empty(process_type, target, yield_profile)
            componentes = recipe.get("components", [])
            total = sum((Decimal(str(c["quantity"])) for c in componentes), Decimal("0"))
            for c in componentes:
                lote, _ = self._flags(c["component_product_id"])
                entradas.append(SnapshotInput(
                    product_id=c["component_product_id"], role=InputRole.COMPONENT,
                    quantity_per_basis=Decimal(str(c["quantity"])), unit_id=c.get("unit_id"),
                    scrap_pct=Decimal(str(c.get("scrap_pct") or "0")),
                    sequence=c.get("sequence") or 0, lot_controlled=lote))
            outs = recipe.get("outputs", [])
            base = sum((Decimal(str(o["quantity"])) for o in outs), Decimal("0")) or Decimal("1")
            for o in outs:
                pct = _dec(o.get("expected_yield_pct"))
                factor = (pct / _HUNDRED if pct is not None
                          else (Decimal(str(o["quantity"])) / total if total > 0
                                else Decimal("0")))
                salidas.append(salida(o["product_id"], o["output_type"], factor,
                                      unidad=o.get("unit_id"), orden=o.get("sequence") or 0,
                                      origen="RECIPE"))
            if not outs:
                salidas.append(salida(target, "MAIN_PRODUCT", Decimal("1"), origen="RECIPE"))
        elif familia is ProcessFamily.PACKAGING:
            logistica = self._profiles.get_logistics(target)
            if packaging_recipe is not None:
                packaging_spec = {"source": "PACKAGING_BOM", "version_id": packaging_recipe["id"],
                                  "materials": [
                                      {"product_id": c["component_product_id"],
                                       "quantity": str(c["quantity"]),
                                       "unit_id": c.get("unit_id")}
                                      for c in packaging_recipe.get("components", [])]}
            elif logistica is not None and logistica.net_weight and logistica.net_weight > 0:
                packaging_spec = {"source": "LOGISTICS_PROFILE",
                                  "net_weight": str(logistica.net_weight),
                                  "weight_unit": logistica.weight_unit}
            entradas.append(fuente())
            salidas.append(salida(target, "MAIN_PRODUCT", Decimal("1"), origen="IDENTITY"))
        else:
            entradas.append(fuente())
            perfil = rendimiento.get(target, {})
            pct = _dec(perfil.get("expected_yield_pct"))
            salidas.append(salida(target, "MAIN_PRODUCT",
                                  pct / _HUNDRED if pct is not None else Decimal("1"),
                                  origen="YIELD_PROFILE" if pct is not None else "IDENTITY"))

        versiones = []
        for etiqueta, fuente_v in (("receta", recipe or packaging_recipe), ("esquema", scheme),
                                   ("rendimiento", yield_profile)):
            if fuente_v:
                versiones.append(f"{etiqueta} v{fuente_v.get('version_number', '?')}")
        return ProcessingRecipeSnapshot(
            process_type=process_type, target_product_id=target,
            inputs=tuple(entradas), outputs=tuple(salidas),
            recipe_version_id=(recipe or packaging_recipe or {}).get("id"),
            cutting_scheme_version_id=(scheme or {}).get("id"),
            yield_profile_version_id=(yield_profile or {}).get("id"),
            packaging_spec=packaging_spec, batch_output_basis=base,
            tolerance_pct=_dec((yield_profile or {}).get("tolerance_pct")),
            technical_parameters=self._classification_of(target),
            effective_version=" · ".join(versiones))

    def _classification_of(self, product_id: str) -> dict:
        """Especie y categoría como DATOS: sirven para resolver tolerancias por
        especie o categoría, nunca para cambiar el comportamiento."""
        dto = self._classification.get(product_id)
        if dto is None:
            return {}
        return {k: v for k, v in (("species_id", dto.species_id),
                                  ("category_id", dto.category_id)) if v}

    @staticmethod
    def _empty(process_type, target, yield_profile) -> ProcessingRecipeSnapshot | None:
        """Nada que ejecutar, pero sí puede haber un perfil de rendimiento: se
        devuelve para que la política diga qué falta en vez de 'nada'."""
        if yield_profile is None:
            return None
        return ProcessingRecipeSnapshot(
            process_type=process_type, target_product_id=target,
            yield_profile_version_id=yield_profile["id"],
            tolerance_pct=_dec(yield_profile.get("tolerance_pct")))
