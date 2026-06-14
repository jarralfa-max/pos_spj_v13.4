"""Canonical product type policy for catalog UI/application flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductTypeRules:
    canonical: str
    label_es: str
    is_composite: bool = False
    is_byproduct: bool = False


class ProductTypePolicy:
    """Centralizes product type labels and operational flags."""

    _RULES = {
        "simple": ProductTypeRules("simple", "Simple"),
        "compuesto": ProductTypeRules("compuesto", "Compuesto", is_composite=True),
        "procesable": ProductTypeRules("procesable", "Procesable"),
        "subproducto": ProductTypeRules("subproducto", "Subproducto", is_byproduct=True),
        "producido": ProductTypeRules("producido", "Producido"),
        "insumo": ProductTypeRules("insumo", "Insumo"),
        "servicio": ProductTypeRules("servicio", "Servicio"),
    }
    _LABEL_TO_CANONICAL = {rule.label_es.lower(): key for key, rule in _RULES.items()}

    @classmethod
    def type_labels_es(cls) -> list[str]:
        return [rule.label_es for rule in cls._RULES.values()]

    @classmethod
    def canonical_from_label(cls, value: str | None) -> str:
        normalized = (value or "simple").strip().lower()
        return cls._LABEL_TO_CANONICAL.get(normalized, normalized if normalized in cls._RULES else "simple")

    @classmethod
    def rules_for(cls, value: str | None) -> ProductTypeRules:
        return cls._RULES[cls.canonical_from_label(value)]
