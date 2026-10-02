"""Reglas del maestro de Productos que TODO documento de compra aplica igual.

Compra rápida y orden de compra validaban distinto (la orden no validaba nada:
ni producto activo, ni unidades, ni almacén de la sucursal). Aquí vive una sola
versión, que ambos casos de uso llaman al crear y — la compra rápida — otra vez al
confirmar.

Los puertos son opcionales para pruebas aisladas; la composición real los inyecta.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.procurement.entities import WEIGHT_PRICING_BASIS


def product_problem(product_catalog, product_id: str, label: str) -> tuple[str, str] | None:
    """``(código, mensaje)`` si el producto no se puede comprar."""
    if product_catalog is None:
        return None
    option = product_catalog.resolve(product_id)
    if option is None:
        return ("PRODUCT_NOT_ACTIVE", f"El producto {label} no está activo; no se puede comprar")
    if not option.purchasable:
        return ("PRODUCT_NOT_PURCHASABLE", f"El producto {label} no está habilitado para compra")
    return None


def warehouse_problem(warehouse_directory, branch_id: str,
                      warehouse_id: str) -> tuple[str, str] | None:
    if warehouse_directory is None:
        return None
    allowed = {wid for wid, _ in warehouse_directory.active_for_branch(branch_id)}
    if warehouse_id not in allowed:
        return ("WAREHOUSE_NOT_IN_BRANCH",
                "El almacén no pertenece a la sucursal de la compra o no admite "
                "recepción de compras")
    return None


def units_from_product_master(raw: dict, product_catalog, *, weight_known: bool = True
                              ) -> tuple[dict, tuple[str, str] | None]:
    """Unidad de inventario y factor salen de Productos, no de la pantalla.

    La línea sólo dice en qué unidad se compró (``purchase_unit``; la base si no
    dice nada). Si el producto no tiene esa presentación configurada se rechaza;
    el factor que haya mandado la UI se ignora siempre. Sin puerto de perfil
    (pruebas aisladas) la línea pasa tal cual."""
    profile_of = getattr(product_catalog, "purchase_profile", None)
    if profile_of is None:
        return raw, None
    profile = profile_of(raw.get("product_id"))
    if profile is None or not profile.base_unit:
        return raw, None   # producto inexistente/inactivo: lo rechaza product_problem
    unit = profile.unit(raw.get("purchase_unit"))
    if unit is None:
        return raw, ("UNIT_NOT_CONFIGURED",
                     f"{profile.name or 'El producto'} no tiene configurada la unidad de compra "
                     f"{raw.get('purchase_unit')}. Configúrala en Productos → Unidades de compra.")
    resolved = dict(raw, purchase_unit=unit.code, inventory_unit=profile.base_unit,
                    conversion_factor=str(unit.factor_to_base))
    weight, problem = _variable_weight(raw, profile, require_weight=weight_known)
    if problem is not None:
        return raw, problem
    resolved.update(weight)
    return resolved, None


#: Bases de precio de Productos que Compras sabe cobrar.
_SUPPORTED_WEIGHT_BASES = (WEIGHT_PRICING_BASIS, "PER_PIECE_WITH_ACTUAL_WEIGHT")


def _variable_weight(raw: dict, profile, *, require_weight: bool = True
                     ) -> tuple[dict, tuple[str, str] | None]:
    """Peso variable (§17) por CAPACIDAD del producto, nunca por categoría
    (§49): si Productos lo marca de peso variable, la línea exige el peso real;
    con base PER_KILOGRAM se cobra el peso (127.850 kg × $95) y, si la unidad de
    inventario es de peso, entra el peso real y no el nominal de la caja. La
    marca la pone Productos: lo que mande la pantalla se ignora."""
    if not getattr(profile, "catch_weight", False):
        return {"pricing_basis": "", "inventory_by_weight": False, "net_weight": None}, None
    basis = getattr(profile, "price_basis", None) or WEIGHT_PRICING_BASIS
    name = profile.name or "El producto"
    if basis not in _SUPPORTED_WEIGHT_BASES:
        return {}, ("PRICE_BASIS_NOT_SUPPORTED",
                    f"{name} tiene base de precio {basis}; Compras sólo cobra por kilogramo "
                    "o por pieza con peso real. Ajústala en Productos → Peso variable.")
    pricing = {"pricing_basis": basis if basis == WEIGHT_PRICING_BASIS else "",
               "inventory_by_weight": getattr(profile, "base_unit_dimension", "") == "WEIGHT"}
    if not require_weight:
        # La orden de compra se emite ANTES de pesar: conoce la base de precio,
        # y el peso real se captura al recibir (§26).
        return dict(pricing, net_weight=None), None
    try:
        weight = Decimal(str(raw.get("net_weight") or "0"))
    except ArithmeticError:
        weight = Decimal("0")
    if weight <= 0:
        return {}, ("WEIGHT_REQUIRED",
                    f"{name} se maneja por peso variable: captura el peso real (kg).")
    return dict(pricing, net_weight=str(weight)), None


def fraction_problem(product_catalog, product_id: str, purchase_unit: str | None,
                     quantities, label: str) -> str | None:
    """§27: si la presentación NO se recibe en fracción (Productos lo decide),
    las cantidades recibidas/aceptadas deben ser unidades completas. La unidad
    base siempre admite fracción. Sin puerto de perfil (pruebas aisladas), no
    se exige nada."""
    profile_of = getattr(product_catalog, "purchase_profile", None)
    if profile_of is None or not purchase_unit:
        return None
    profile = profile_of(product_id)
    unit = profile.unit(purchase_unit) if profile is not None else None
    if unit is None or unit.is_base or getattr(unit, "fractional_receipt", True):
        return None
    for value in quantities:
        try:
            quantity = Decimal(str(value))
        except ArithmeticError:
            continue
        if quantity != quantity.to_integral_value():
            name = profile.name or label or "El producto"
            return (f"{name} se recibe en {unit.name.lower()} completos: captura "
                    f"{quantity.to_integral_value(rounding='ROUND_FLOOR')} o "
                    f"{quantity.to_integral_value(rounding='ROUND_CEILING')}, o cambia la "
                    "política en Productos → Unidades de compra.")
    return None


def inventory_unit_cost(unit_cost: Decimal, conversion_factor) -> Decimal:
    """Costo por unidad de INVENTARIO: una caja de 20 kg a $400 son $20/kg."""
    factor = Decimal(str(conversion_factor or "1"))
    return unit_cost / factor if factor else unit_cost
