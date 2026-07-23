"""Unit conversion policy (§16) — a conversion graph with no cycles.

Conversions form a directed graph (from_unit → to_unit, weight ``factor``). The
policy rejects cycles (§16 "impedir ciclos") and can resolve a Decimal conversion
between two units by walking the graph (following factors and their inverses).
Pure: no persistence, no float.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.product_unit_conversion import (
    ProductUnitConversion,
)
from backend.domain.products.exceptions import (
    UnitConversionCycleError,
    UnitConversionNotFoundError,
)


def _adjacency(conversions: list[ProductUnitConversion]) -> dict[str, list[tuple[str, Decimal]]]:
    """Undirected reachability with directional factors (edge + inverse edge)."""
    graph: dict[str, list[tuple[str, Decimal]]] = {}
    for c in conversions:
        graph.setdefault(c.from_unit_id, []).append((c.to_unit_id, c.factor))
        graph.setdefault(c.to_unit_id, []).append((c.from_unit_id, c.inverse_factor()))
    return graph


def detect_cycle(conversions: list[ProductUnitConversion]) -> None:
    """Raise if the *directed* conversion graph contains a cycle (§16)."""
    directed: dict[str, list[str]] = {}
    for c in conversions:
        directed.setdefault(c.from_unit_id, []).append(c.to_unit_id)
        directed.setdefault(c.to_unit_id, [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in directed}

    def visit(node: str) -> None:
        color[node] = GRAY
        for nxt in directed.get(node, []):
            if color[nxt] == GRAY:
                raise UnitConversionCycleError(
                    f"Ciclo de conversión detectado en la unidad {nxt}")
            if color[nxt] == WHITE:
                visit(nxt)
        color[node] = BLACK

    for node in list(directed):
        if color[node] == WHITE:
            visit(node)


def convert(
    quantity: Decimal | int | str,
    *,
    from_unit_id: str,
    to_unit_id: str,
    conversions: list[ProductUnitConversion],
    rounding_scale: int = 6,
) -> Decimal:
    """Convert ``quantity`` from one unit to another following the graph."""
    if isinstance(quantity, bool) or isinstance(quantity, float):
        raise UnitConversionNotFoundError("La cantidad no puede ser float")
    q = Decimal(str(quantity))
    if from_unit_id == to_unit_id:
        return q
    graph = _adjacency(conversions)
    # BFS acumulando el factor multiplicativo a lo largo del camino
    seen = {from_unit_id}
    frontier: list[tuple[str, Decimal]] = [(from_unit_id, Decimal(1))]
    while frontier:
        unit, acc = frontier.pop(0)
        for nxt, factor in graph.get(unit, []):
            if nxt in seen:
                continue
            new_acc = acc * factor
            if nxt == to_unit_id:
                result = q * new_acc
                return result.quantize(Decimal(1).scaleb(-int(rounding_scale)))
            seen.add(nxt)
            frontier.append((nxt, new_acc))
    raise UnitConversionNotFoundError(
        f"No existe conversión de {from_unit_id} a {to_unit_id}")
