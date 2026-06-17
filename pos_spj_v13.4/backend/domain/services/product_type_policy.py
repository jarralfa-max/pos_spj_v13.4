"""Canonical product type policy for catalog UI/application flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductTypeRules:
    canonical: str
    label_es: str
    is_composite: bool = False
    is_byproduct: bool = False
    allows_recipe: bool = False
    deducts_components_on_sale: bool = False
    is_inventory_tracked: bool = True
    is_sellable: bool = True


class ProductTypePolicy:
    """Centralizes product type labels and operational flags."""

    _RULES = {
        "simple": ProductTypeRules("simple", "Simple"),
        "compuesto": ProductTypeRules("compuesto", "Compuesto", is_composite=True, allows_recipe=True, deducts_components_on_sale=True),
        "procesable": ProductTypeRules("procesable", "Procesable", allows_recipe=True),
        "subproducto": ProductTypeRules("subproducto", "Subproducto", is_byproduct=True),
        "producido": ProductTypeRules("producido", "Producido"),
        "insumo": ProductTypeRules("insumo", "Insumo", is_sellable=False),
        "servicio": ProductTypeRules("servicio", "Servicio", is_inventory_tracked=False),
    }
    _LABEL_TO_CANONICAL = {rule.label_es.lower(): key for key, rule in _RULES.items()}

    @classmethod
    def type_labels_es(cls) -> list[str]:
        return [rule.label_es for rule in cls._RULES.values()]

    @classmethod
    def spanish_labels(cls) -> tuple[str, ...]:
        return tuple(rule.label_es for rule in cls._RULES.values())

    @classmethod
    def canonical_from_label(cls, value: str | None) -> str:
        normalized = (value or "simple").strip().lower()
        return cls._LABEL_TO_CANONICAL.get(normalized, normalized if normalized in cls._RULES else "simple")

    @classmethod
    def normalize(cls, value: str | None) -> str:
        """Alias for canonical_from_label."""
        return cls.canonical_from_label(value)

    @classmethod
    def rules_for(cls, value: str | None) -> ProductTypeRules:
        return cls._RULES[cls.canonical_from_label(value)]
