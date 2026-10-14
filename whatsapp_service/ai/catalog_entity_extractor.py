from __future__ import annotations
from decimal import Decimal
try:
    from domain.money import to_decimal
except ImportError:  # importado como paquete `whatsapp_service.`
    from whatsapp_service.domain.money import to_decimal

import re
from typing import Any, Dict, List

_PRODUCT_UNITS = {
    "kg", "kilo", "kilos", "kgs",
    "pza", "pzas", "pieza", "piezas",
    "paquete", "paquetes", "caja", "cajas", "bolsa", "bolsas",
}
_TIME_MARKERS = {
    "a", "alas", "las", "la", "pm", "am", "hrs", "hr", "hora", "horas",
    "manana", "tarde", "noche", "mediodia", "medio",
}
_NUMBER_WORDS = {
    "un": Decimal("1"), "una": Decimal("1"), "uno": Decimal("1"),
    "dos": Decimal("2"), "tres": Decimal("3"), "cuatro": Decimal("4"), "cinco": Decimal("5"),
    "seis": Decimal("6"), "siete": Decimal("7"), "ocho": Decimal("8"), "nueve": Decimal("9"),
    "diez": Decimal("10"), "once": Decimal("11"), "doce": Decimal("12"), "trece": Decimal("13"),
    "catorce": Decimal("14"), "quince": Decimal("15"), "dieciseis": Decimal("16"),
    "diecisiete": Decimal("17"), "dieciocho": Decimal("18"), "diecinueve": Decimal("19"),
    "veinte": Decimal("20"),
    "media": Decimal("0.5"), "medio": Decimal("0.5"),
}
_NUM_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
_CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


class CatalogEntityExtractor:
    """Catalog-backed product entity extractor for WhatsApp messages.

    Separates product quantities from scheduled times. Supports numeric and
    Spanish written quantities like "dos kilos", "un kilo", "medio kilo",
    "kilo y medio" while ignoring time phrases like "a las dos".
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
        # REGLA CERO: el id de producto es UUIDv7 (str). Antes se convertía el id
        # a entero, lo que lanzaba ValueError con IDs UUID → el except dejaba el
        # catálogo vacío y ningún producto era reconocido.
        seen: set[str] = set()
        for product in sorted(catalog, key=lambda p: len(str(p.get("nombre", ""))), reverse=True):
            pid = str(product.get("id") or "").strip()
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
            qty = out.get("cantidad_solicitada") or out.get("cantidad") or out.get("quantity") or out.get("qty") or 1
            out["cantidad_solicitada"] = self._coerce_quantity(qty)
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
        qty = prod.get("cantidad_solicitada") or prod.get("quantity") or prod.get("cantidad") or prod.get("qty") or 1
        unit = prod.get("unidad_solicitada") or prod.get("unit") or prod.get("unidad") or "kg"
        out = dict(match)
        out["cantidad_solicitada"] = self._coerce_quantity(qty)
        out["unidad_solicitada"] = self._unit(unit)
        return out

    def _mentioned(self, name: str, text_norm: str) -> bool:
        name_norm = self._norm(name)
        if name_norm and name_norm in text_norm:
            return True
        words = [w for w in name_norm.split() if len(w) >= 4]
        return any((" " + w + " ") in (" " + text_norm + " ") for w in words)

    def _quantity_for_product(self, text: str, name: str, default_unit: str) -> tuple[Decimal, str]:
        tokens = self._tokens(text)
        name_tokens = self._tokens(name)
        if not tokens or not name_tokens:
            return Decimal("1"), self._unit(default_unit)

        product_idx = self._find_product_index(tokens, name_tokens)
        candidates: List[tuple[int, Decimal, str]] = []
        units_normalized = {self._unit(u) for u in _PRODUCT_UNITS}
        for i, token in enumerate(tokens):
            qty = self._quantity_token_value(tokens, i)
            if qty is None:
                continue
            if self._looks_like_time(tokens, i):
                continue

            unit = self._unit(tokens[i + 1]) if i + 1 < len(tokens) else ""
            has_product_unit = unit in units_normalized
            distance = abs(i - product_idx) if product_idx >= 0 else 99

            # "dos kilos de pechuga", "2 kg pechuga", "medio kilo pechuga".
            if has_product_unit and (product_idx < 0 or distance <= 6):
                candidates.append((distance, qty, unit))
                continue

            # "kilo y medio de pechuga" / "kg y medio pechuga".
            if token in units_normalized and i + 2 < len(tokens) and tokens[i + 1] == "y" and tokens[i + 2] in {"medio", "media"}:
                distance = abs(i - product_idx) if product_idx >= 0 else 99
                if product_idx < 0 or distance <= 6:
                    candidates.append((distance, Decimal("1.5"), self._unit(token)))
                continue

            # Compact pattern: "pechuga dos", "dos pechuga", but not "pechuga a las dos".
            if not has_product_unit and product_idx >= 0 and distance <= 2:
                if i > 0 and tokens[i - 1] in _TIME_MARKERS:
                    continue
                candidates.append((distance + 2, qty, self._unit(default_unit)))

        if candidates:
            _, qty, unit = sorted(candidates, key=lambda x: x[0])[0]
            return qty, unit
        return Decimal("1"), self._unit(default_unit)

    def _quantity_token_value(self, tokens: List[str], i: int) -> Decimal | None:
        token = tokens[i]
        if _NUM_RE.match(token):
            return to_decimal(token.replace(",", "."))
        if token in _NUMBER_WORDS:
            return _NUMBER_WORDS[token]
        # veinte y uno / treinta not supported yet; fail closed instead of guessing.
        return None

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

    def _coerce_quantity(self, value: Any) -> Decimal:
        if isinstance(value, (int, Decimal)):
            return to_decimal(value)
        text = self._norm(str(value))
        if _NUM_RE.match(text):
            return to_decimal(text.replace(",", "."))
        if text in _NUMBER_WORDS:
            return _NUMBER_WORDS[text]
        return Decimal("1")

    def _unit(self, unit: str) -> str:
        unit = (unit or "kg").lower().strip(".,")
        if unit in ("kilo", "kilos", "kgs"):
            return "kg"
        if unit in ("pza", "pzas", "pieza", "piezas"):
            return "pieza"
        return unit or "kg"
