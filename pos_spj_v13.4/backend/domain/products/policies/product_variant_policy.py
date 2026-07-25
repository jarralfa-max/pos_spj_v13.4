"""Variant generation policy (P1-03) — pura: producto cartesiano de ejes.

Dado un conjunto de ejes (atributo → lista de opciones seleccionadas), produce todas
las combinaciones. No toca persistencia; el caso de uso crea un producto hijo por
combinación que aún no exista. Offline por diseño.
"""

from __future__ import annotations

from itertools import product

from backend.domain.products.exceptions import InvalidVariantError

#: Tope de combinaciones por generación para evitar explosiones accidentales.
MAX_COMBINATIONS = 500


def cartesian_combinations(
    axes: list[tuple[str, list[str]]],
) -> list[tuple[tuple[str, str], ...]]:
    """``axes`` = [(attribute_id, [option_id, …]), …] → lista de combinaciones.

    Cada combinación es una tupla de pares ``(attribute_id, option_id)``, una por
    eje. Lanza ``InvalidVariantError`` si no hay ejes, algún eje va sin opciones, o
    el total excede ``MAX_COMBINATIONS``.
    """
    if not axes:
        raise InvalidVariantError("Se requiere al menos un eje de variación")
    total = 1
    for attribute_id, options in axes:
        if not options:
            raise InvalidVariantError(
                "Cada eje debe tener al menos una opción seleccionada")
        total *= len(options)
    if total > MAX_COMBINATIONS:
        raise InvalidVariantError(
            f"La generación produciría {total} variantes (máximo {MAX_COMBINATIONS})")
    option_lists = [[(attr, opt) for opt in options] for attr, options in axes]
    return [tuple(combo) for combo in product(*option_lists)]
