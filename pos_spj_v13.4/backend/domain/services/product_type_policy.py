"""Canonical product type policy for catalog UI/application flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductTypeRules:
    canonical: str
    label_es: str
    help_es: str
    is_composite: bool = False
    is_byproduct: bool = False
    allows_recipe: bool = False
    allows_virtual_stock: bool = False
    deducts_components_on_sale: bool = False
    is_inventory_tracked: bool = True
    is_sellable: bool = True


class ProductTypePolicy:
    """Centralizes product type labels, help texts and operational flags."""

    _RULES = {
        "simple": ProductTypeRules(
            canonical="simple",
            label_es="Simple",
            help_es="Producto independiente. Se vende tal cual, sin componentes ni receta.",
        ),
        "compuesto": ProductTypeRules(
            canonical="compuesto",
            label_es="Compuesto",
            help_es="Armado a partir de otros productos. Al venderlo descuenta sus componentes del inventario.",
            is_composite=True,
            allows_recipe=True,
            deducts_components_on_sale=True,
        ),
        "procesable": ProductTypeRules(
            canonical="procesable",
            label_es="Procesable",
            help_es="Requiere un proceso de transformación antes de su venta. Define su receta de insumos.",
            allows_recipe=True,
        ),
        "subproducto": ProductTypeRules(
            canonical="subproducto",
            label_es="Subproducto",
            help_es="Resultado secundario de un proceso de producción. Ingresa al inventario como derivado.",
            is_byproduct=True,
        ),
        "producido": ProductTypeRules(
            canonical="producido",
            label_es="Producido",
            help_es="Producto terminado generado por el módulo de producción. Su stock se controla por lotes.",
        ),
        "insumo": ProductTypeRules(
            canonical="insumo",
            label_es="Insumo",
            help_es="Materia prima o insumo interno. No se vende directamente al cliente.",
            is_sellable=False,
        ),
        "servicio": ProductTypeRules(
            canonical="servicio",
            label_es="Servicio",
            help_es="Prestación de servicio. No genera movimientos de inventario.",
            is_inventory_tracked=False,
        ),
    }
    _LABEL_TO_CANONICAL: dict[str, str] = {
        rule.label_es.lower(): key for key, rule in _RULES.items()
    }

    @classmethod
    def type_labels_es(cls) -> list[str]:
        return [rule.label_es for rule in cls._RULES.values()]

    @classmethod
    def spanish_labels(cls) -> tuple[str, ...]:
        return tuple(rule.label_es for rule in cls._RULES.values())

    @classmethod
    def canonical_from_label(cls, value: str | None) -> str:
        normalized = (value or "simple").strip().lower()
        return cls._LABEL_TO_CANONICAL.get(
            normalized,
            normalized if normalized in cls._RULES else "simple",
        )

    @classmethod
    def normalize(cls, value: str | None) -> str:
        """Alias for canonical_from_label."""
        return cls.canonical_from_label(value)

    @classmethod
    def rules_for(cls, value: str | None) -> ProductTypeRules:
        return cls._RULES[cls.canonical_from_label(value)]
