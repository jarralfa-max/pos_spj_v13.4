from __future__ import annotations

import re
from typing import Any, Dict, List

_PRODUCT_UNITS = {
    "kg", "kilo", "kilos", "kgs",
    "pza", "pzas", "pieza", "piezas",
    "paquete", "paquetes", "caja", "cajas", "bolsa", "bolsas",
}
_TIME_MARKERS = {
    "a", "alas", "las", "la", "pm", "am", "hrs", "hr", "hora", "horas",
    "mañana", "tarde", "noche", "mediodia", "medio",
}
_NUM_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
_CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


class CatalogEntityExtractor:
    """Catalog-backed product entity extractor for WhatsApp messages.

    This extractor deliberately separates product quantities from scheduled
    times. A number is treated as quantity only when it is tied to a product
    unit or appears immediately before/after the product mention without time
    markers such as "a las", "pm", "am" or "hrs".
    """

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
            qty, unit = self._quantity_for_product(text, name, product.get("unidad") or "kg")
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
            qty = out.get("cantidad_solicitada") or out.get("cantidad") or out.get("quantity") or out.get("qty") or 1.0
            out["cantidad_solicitada"] = float(qty or 1.0)
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

    def _quantity_for_product(self, text: str, name: str, default_unit: str) -> tuple[float, str]:
        tokens = self._tokens(text)
        name_tokens = self._tokens(name)
        if not tokens or not name_tokens:
            return 1.0, self._unit(default_unit)

        product_idx = self._find_product_index(tokens, name_tokens)
        candidates: List[tuple[int, float, str]] = []
        for i, token in enumerate(tokens):
            if not _NUM_RE.match(token):
                continue
            if self._looks_like_time(tokens, i):
                continue
            unit = self._unit(tokens[i + 1]) if i + 1 < len(tokens) else ""
            has_product_unit = unit in {self._unit(u) for u in _PRODUCT_UNITS}
            distance = abs(i - product_idx) if product_idx >= 0 else 99

            # Strong pattern: "2 kilos de pechuga" / "2 kg pechuga".
            if has_product_unit and (product_idx < 0 or distance <= 5):
                candidates.append((distance, float(token.replace(",", ".")), unit))
                continue

            # Compact pattern: "pechuga 2" or "2 pechuga".
            if not has_product_unit and product_idx >= 0 and distance <= 2:
                # Avoid phrases like "pechuga a las 2".
                if i > 0 and tokens[i - 1] in _TIME_MARKERS:
                    continue
                candidates.append((distance + 2, float(token.replace(",", ".")), self._unit(default_unit)))

        if candidates:
            _, qty, unit = sorted(candidates, key=lambda x: x[0])[0]
            return qty, unit
        return 1.0, self._unit(default_unit)

    def _looks_like_time(self, tokens: List[str], i: int) -> bool:
        token = tokens[i]
        if _CLOCK_RE.match(token):
            return True
        prev1 = tokens[i - 1] if i - 1 >= 0 else ""
        prev2 = tokens[i - 2] if i - 2 >= 0 else ""
        next1 = tokens[i + 1] if i + 1 < len(tokens) else ""
        next2 = tokens[i + 2] if i + 2 < len(tokens) else ""
        if prev1 in {"las", "la"} and prev2 in {"a", "para"}:
            return True
        if prev1 in {"a", "alas", "para"}:
            return True
        if next1 in {"am", "pm", "hrs", "hr", "hora", "horas"}:
            return True
        if next1 in {"de"} and next2 in {"la", "el"}:
            return True
        return False

    def _find_product_index(self, tokens: List[str], name_tokens: List[str]) -> int:
        if not name_tokens:
            return -1
        for i in range(0, max(len(tokens) - len(name_tokens) + 1, 0)):
            if tokens[i:i + len(name_tokens)] == name_tokens:
                return i
        # Fallback: any strong product word.
        strong = [w for w in name_tokens if len(w) >= 4]
        for i, token in enumerate(tokens):
            if token in strong:
                return i
        return -1

    def _tokens(self, value: str) -> List[str]:
        return self._norm(value).replace(":", " ").split()

    def _norm(self, value: str) -> str:
        value = (value or "").lower()
        for src, dst in zip("áéíóúüñ", "aeiouun"):
            value = value.replace(src, dst)
        clean = []
        for char in value:
            clean.append(char if char.isalnum() or char.isspace() or char in ":,." else " ")
        return " ".join("".join(clean).split())

    def _unit(self, unit: str) -> str:
        unit = (unit or "kg").lower().strip(".,")
        if unit in ("kilo", "kilos", "kgs"):
            return "kg"
        if unit in ("pza", "pzas", "pieza", "piezas"):
            return "pieza"
        return unit or "kg"
