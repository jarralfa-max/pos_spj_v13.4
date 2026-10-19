"""Código impreso del contenedor, asignado por el sistema (2026-10-17).

Antes se capturaba a mano y la base real ya tenía «CAJ-0001» y «CAJ-001» para
dos cajas iguales. Ahora el código es ``<prefijo>-<número de 6 dígitos>``: el
prefijo sale de la categoría del tipo (CJ = caja plástica, TR = tarima, …) y el
número es el siguiente de ese prefijo. Los códigos ya capturados se conservan.
"""

from __future__ import annotations

import re
from typing import Iterable

CATEGORY_PREFIX = {
    "PLASTIC_BOX": "CJ", "CARDBOARD_BOX": "CC", "PALLET": "TR", "CAGE": "JA",
    "CRATE": "RJ", "TOTE": "CA", "COOLER": "HI", "TRAY": "CH", "BAG": "BO",
    "BIN": "GR", "MASTER_CONTAINER": "CM", "TRAILER_CONTAINER": "CT",
}
DEFAULT_PREFIX = "CT"
DIGITS = 6


def prefix_for_category(category: str | None) -> str:
    return CATEGORY_PREFIX.get(str(category or "").upper(), DEFAULT_PREFIX)


def next_code(prefix: str, existing_codes: Iterable[str]) -> str:
    """El siguiente código libre del prefijo (máximo existente + 1)."""
    patron = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    mayor = 0
    for code in existing_codes:
        hallado = patron.match(str(code or "").strip().upper())
        if hallado:
            mayor = max(mayor, int(hallado.group(1)))
    return f"{prefix}-{mayor + 1:0{DIGITS}d}"
