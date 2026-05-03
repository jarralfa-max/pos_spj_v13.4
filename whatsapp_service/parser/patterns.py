# parser/patterns.py — Patrones regex para extraer intenciones y entidades
"""
Nivel 2 del motor NLP: regex + keywords.
Solo se usa cuando el mensaje es texto libre (no botón interactivo).
"""
import re
from typing import List, Tuple

# ── Intenciones por keyword ───────────────────────────────────────────────────
INTENT_KEYWORDS = {
    "pedido": [
        r"\bpedir\b", r"\bpedido\b", r"\bquiero\b", r"\bm[aá]ndame\b",
        r"\bnecesito\b", r"\benv[ií]ame\b", r"\bordenar\b", r"\borden\b",
        r"\bcomprar\b", r"\bquiero comprar\b",
    ],
    "cotizacion": [
        r"\bcotiza\b", r"\bcotizaci[oó]n\b", r"\bpresupuesto\b",
        r"\bcu[aá]nto (?:me )?(?:sale|cuesta|costar[ií]a)\b",
        r"\bprecio\b",
    ],
    "repetir": [
        r"\brepetir\b", r"\blo mismo\b", r"\bigual que\b",
        r"\blo de siempre\b", r"\botro igual\b", r"\blo de la vez pasada\b",
    ],
    "estado_pedido": [
        r"\bestado\b", r"\bd[oó]nde (?:est[aá]|va)\b", r"\bmi pedido\b",
        r"\brastrear\b", r"\bseguimiento\b",
    ],
    "cancelar": [
        r"\bcancelar\b", r"\bno quiero\b", r"\bolv[ií]da(?:lo)?\b",
        r"\bya no\b", r"\bdejar?\b",
    ],
    "saludo": [
        r"^hola\b", r"^buenos? (?:d[ií]as?|tardes?|noches?)\b",
        r"^hey\b", r"^qu[eé] tal\b", r"^buen d[ií]a\b",
    ],
    "ayuda": [
        r"\bayuda\b", r"\bmen[uú]\b", r"\bopciones\b",
        r"\bqu[eé] puedo\b", r"\bc[oó]mo funciona\b",
    ],
    "pago": [
        r"\bpagar\b", r"\bpago\b", r"\btransferencia\b",
        r"\bcuenta\b.*\bpagar\b", r"\banticipo\b",
    ],
    "sucursal": [
        r"\bsucursal\b", r"\bcambiar sucursal\b", r"\botra sucursal\b",
    ],
    "gracias": [
        r"\bgracias\b", r"\bchido\b", r"\bgeni?al\b",
        r"\bok\b", r"\bperfecto\b",
    ],
}

# ── Patrón para extraer productos + cantidades ───────────────────────────────
# "5 kilos de pechuga" | "2 piernas" | "pechuga 3kg" | "3.5 kg arrachera"
PRODUCT_PATTERNS = [
    # "5 kilos de pechuga"
    re.compile(
        r'(\d+(?:[.,]\d+)?)\s*'
        r'(?:kg|kilos?|kgs?|pzas?|piezas?|paquetes?|cajas?|bolsas?)?\s*'
        r'(?:de\s+)?'
        r'([a-záéíóúñü]{3,}(?:\s+(?:de\s+)?[a-záéíóúñü]+)*)',
        re.IGNORECASE
    ),
    # "pechuga 5kg"
    re.compile(
        r'([a-záéíóúñü]{3,}(?:\s+(?:de\s+)?[a-záéíóúñü]+)*)\s+'
        r'(\d+(?:[.,]\d+)?)\s*'
        r'(?:kg|kilos?|kgs?|pzas?|piezas?)?',
        re.IGNORECASE
    ),
]

# ── Patrón para números sueltos (respuesta a "¿cuántos kilos?") ──────────────
NUMBER_PATTERN = re.compile(r'^(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|pzas?|piezas?)?$', re.IGNORECASE)

# ── Patrón para selección numérica ("1", "2", "3") ──────────────────────────
SELECTION_PATTERN = re.compile(r'^(\d{1,2})$')


def detect_intent(text: str) -> Tuple[str, float]:
    """Detecta la intención del texto. Retorna (intent, confidence)."""
    text_lower = text.lower().strip()

    for intent, patterns in INTENT_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent, 0.85
    return "unknown", 0.0


def extract_product_mentions(text: str) -> List[dict]:
    """
    Extrae menciones de productos del texto libre.
    Retorna [{nombre_raw, cantidad, unidad}, ...]
    """
    results = []
    text_clean = text.lower().strip()

    for pattern in PRODUCT_PATTERNS:
        for match in pattern.finditer(text_clean):
            groups = match.groups()
            # Determinar cuál grupo es número y cuál es nombre
            if groups[0][0].isdigit():
                qty_str, name = groups[0], groups[1]
            else:
                name, qty_str = groups[0], groups[1]

            qty = float(qty_str.replace(",", "."))
            name = name.strip()

            # Filtrar palabras comunes que no son productos
            if name in ("de", "la", "el", "los", "las", "un", "una", "y", "con", "para"):
                continue

            results.append({
                "nombre_raw": name,
                "cantidad": qty,
                "unidad": "kg",
            })

    return results


def extract_number(text: str) -> float:
    """Extrae un número del texto. Retorna 0 si no encuentra."""
    m = NUMBER_PATTERN.match(text.strip())
    if m:
        return float(m.group(1).replace(",", "."))
    return 0.0


def extract_selection(text: str) -> int:
    """Extrae una selección numérica (1, 2, 3...). Retorna 0 si no es."""
    m = SELECTION_PATTERN.match(text.strip())
    return int(m.group(1)) if m else 0
