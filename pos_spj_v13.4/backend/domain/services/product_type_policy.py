"""Product type policy rules for the catalog domain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductTypeRules:
    code: str
    label_es: str
    is_sellable: bool
    is_inventory_tracked: bool
    allows_recipe: bool
    allows_virtual_stock: bool
    deducts_components_on_sale: bool
    is_composite: bool = False
    is_byproduct: bool = False
    recipe_kind: str | None = None
    help_es: str = ""


class ProductTypePolicy:
    """Centralized rules for product type behavior.

    The UI keeps Spanish labels, while the backend persists canonical English-ish
    lowercase codes used by services and future API endpoints.
    """

    _RULES: dict[str, ProductTypeRules] = {
        "simple": ProductTypeRules(
            code="simple",
            label_es="Simple",
            is_sellable=True,
            is_inventory_tracked=True,
            allows_recipe=False,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            help_es="Producto que se compra y vende directamente.",
        ),
        "compuesto": ProductTypeRules(
            code="compuesto",
            label_es="Compuesto",
            is_sellable=True,
            is_inventory_tracked=False,
            allows_recipe=True,
            allows_virtual_stock=True,
            deducts_components_on_sale=True,
            is_composite=True,
            recipe_kind="COMBINACION",
            help_es="Producto vendido como paquete/combo. Puede descontar componentes al venderse.",
        ),
        "procesable": ProductTypeRules(
            code="procesable",
            label_es="Procesable",
            is_sellable=False,
            is_inventory_tracked=True,
            allows_recipe=True,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            recipe_kind="SUBPRODUCTO",
            help_es="Producto que puede transformarse en subproductos. Ejemplo: pollo entero.",
        ),
        "subproducto": ProductTypeRules(
            code="subproducto",
            label_es="Subproducto",
            is_sellable=True,
            is_inventory_tracked=True,
            allows_recipe=True,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            is_byproduct=True,
            recipe_kind="SUBPRODUCTO",
            help_es="Producto generado por un despiece o usado como componente de otros productos.",
        ),
        "producido": ProductTypeRules(
            code="producido",
            label_es="Producido",
            is_sellable=True,
            is_inventory_tracked=True,
            allows_recipe=True,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            recipe_kind="PRODUCCION",
            help_es="Producto elaborado a partir de insumos o subproductos.",
        ),
        "insumo": ProductTypeRules(
            code="insumo",
            label_es="Insumo",
            is_sellable=False,
            is_inventory_tracked=True,
            allows_recipe=False,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            help_es="Producto usado como ingrediente/material.",
        ),
        "servicio": ProductTypeRules(
            code="servicio",
            label_es="Servicio",
            is_sellable=True,
            is_inventory_tracked=False,
            allows_recipe=False,
            allows_virtual_stock=False,
            deducts_components_on_sale=False,
            help_es="No controla inventario físico.",
        ),
    }
    _SPANISH_TO_CODE = {rules.label_es.lower(): code for code, rules in _RULES.items()}

    @classmethod
    def normalize(cls, product_type: str | None) -> str:
        value = (product_type or "simple").strip().lower()
        value = cls._SPANISH_TO_CODE.get(value, value)
        if value not in cls._RULES:
            raise ValueError(f"Unsupported product type: {product_type}")
        return value

    @classmethod
    def rules_for(cls, product_type: str | None) -> ProductTypeRules:
        return cls._RULES[cls.normalize(product_type)]

    @classmethod
    def spanish_labels(cls) -> tuple[str, ...]:
        return tuple(rules.label_es for rules in cls._RULES.values())

    @classmethod
    def recipe_allowed(cls, product_type: str | None) -> bool:
        return cls.rules_for(product_type).allows_recipe
