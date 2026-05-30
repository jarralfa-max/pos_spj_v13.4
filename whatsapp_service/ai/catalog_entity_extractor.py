from __future__ import annotations

from typing import Any, Dict, List


class CatalogEntityExtractor:
    """Catalog-backed product entity extractor for WhatsApp messages."""

    def __init__(self, matcher):
        self.matcher = matcher

    def extract_products(self, text: str) -> List[Dict[str, Any]]:
        text_norm = self._norm(text)
        catalog = getattr(self.matcher, "_cache", []) or []
        if not catalog:
            try:
                self.matcher.reload()
                catalog = getattr(self.matcher, "_cache", []) or []
            except Exception:
                catalog = []
        entities: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for product in sorted(catalog, key=lambda p: len(str(p.get("nombre", ""))), reverse=True):
            pid = int(product.get("id", 0) or 0)
            if not pid or pid in seen:
                continue
            name = str(product.get("nombre", "")).strip()
            if not name or not self._mentioned(name, text_norm):
                continue
            qty, unit = self._quantity(text, name)
            entity = dict(product)
            entity["cantidad_solicitada"] = qty
            entity["unidad_solicitada"] = unit or entity.get("unidad") or "kg"
            entities.append(entity)
            seen.add(pid)
        return entities

    def normalize_product(self, prod: Dict[str, Any]) -> Dict[str, Any] | None:
        if not isinstance(prod, dict):
            return None
        if prod.get("id"):
            out = dict(prod)
            out.setdefault("cantidad_solicitada", out.get("cantidad", 1.0) or 1.0)
            out.setdefault("unidad_solicitada", out.get("unidad", "kg") or "kg")
            return out
        name = str(prod.get("nombre") or prod.get("product_name") or prod.get("nombre_raw") or prod.get("name") or "").strip()
        if not name:
            return None
        try:
            match = self.matcher.match_single(name)
        except Exception:
            match = None
        if not match:
            return None
        qty = prod.get("cantidad_solicitada") or prod.get("quantity") or prod.get("cantidad") or prod.get("qty") or 1.0
        unit = prod.get("unidad_solicitada") or prod.get("unit") or prod.get("unidad") or "kg"
        out = dict(match)
        out["cantidad_solicitada"] = float(qty or 1.0)
        out["unidad_solicitada"] = self._unit(unit)
        return out

    def _mentioned(self, name: str, text_norm: str) -> bool:
        name_norm = self._norm(name)
        if name_norm and name_norm in text_norm:
            return True
        words = [w for w in name_norm.split() if len(w) >= 4]
        return any((" " + w + " ") in (" " + text_norm + " ") for w in words)

    def _quantity(self, text: str, name: str) -> tuple[float, str]:
        tokens = text.replace(",", ".").split()
        for i, token in enumerate(tokens):
            try:
                qty = float(token)
            except Exception:
                continue
            unit = tokens[i + 1] if i + 1 < len(tokens) else "kg"
            return qty, self._unit(unit)
        return 1.0, "kg"

    def _norm(self, value: str) -> str:
        value = (value or "").lower()
        for src, dst in zip("áéíóúüñ", "aeiouun"):
            value = value.replace(src, dst)
        clean = []
        for char in value:
            clean.append(char if char.isalnum() or char.isspace() else " ")
        return " ".join("".join(clean).split())

    def _unit(self, unit: str) -> str:
        unit = (unit or "kg").lower()
        if unit in ("kilo", "kilos", "kgs"):
            return "kg"
        if unit in ("pza", "pzas", "pieza", "piezas"):
            return "pieza"
        return unit or "kg"
