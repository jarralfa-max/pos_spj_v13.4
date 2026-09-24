"""MeatLotTraceabilityQueryService — de qué salió un lote producido y a dónde fue.

POR QUÉ NO UN GRAFO PROPIO
--------------------------
La genealogía de lotes ya es de Inventario: `RegisterTraceabilityLinkUseCase`
escribe los enlaces (el adaptador de recepción de producción de Cárnico los
registra al recibir cada salida, con los lotes de entrada consumidos) y
`TraceabilityQueryService` los recorre, incluido el informe de retiro. Esta
consulta NO reimplementa esa travesía: la compone.

Lo que sí es de Cárnico es el QUÉ preguntar: qué lotes produjo esta sucursal —
`processing_output_results`, la misma tabla que alimenta Rendimientos → Por
corte—, con qué insumo entraron y en qué orden se produjeron. Un lote que no
salió de una orden de la sucursal no se traza aquí: devuelve `None` en vez de
enseñar la producción de otra sucursal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProducedLot:
    """Un lote producido por una orden de la sucursal."""

    lot_id: str
    product_name: str
    output_type: str
    weight: str
    produced_at: str
    processing_order_id: str
    process_type: str


@dataclass(frozen=True, slots=True)
class LotInput:
    """Lote de entrada que la orden consumió para producir el lote trazado."""

    lot_id: str
    product_name: str
    weight: str


@dataclass(frozen=True, slots=True)
class LotDestination:
    """Movimiento aguas abajo del lote, tal como lo reporta Inventario."""

    occurred_at: str
    movement_type: str
    source_module: str
    source_document_type: str
    source_document_id: str
    branch_id: str
    quantity: str
    weight: str


@dataclass(frozen=True, slots=True)
class ChainedConsumption:
    """El lote entró como INSUMO de otra orden: el encadenamiento entre órdenes
    que registra `ChainOutputAsConsumptionUseCase` (PROC-18)."""

    processing_order_id: str
    process_type: str
    product_name: str
    quantity: str
    weight: str
    linked_at: str


@dataclass(frozen=True, slots=True)
class MeatLotTrace:
    produced: ProducedLot
    inputs: tuple[LotInput, ...] = ()
    destinations: tuple[LotDestination, ...] = ()
    #: Órdenes de Cárnico que consumieron este lote (grafo entre órdenes).
    chained: tuple[ChainedConsumption, ...] = ()
    #: Lotes alcanzados aguas abajo (el propio incluido), de `recall_report`.
    affected_lots: tuple[str, ...] = ()
    reaches_customers: bool = False
    branches_touched: tuple[str, ...] = ()
    #: Lotes padre registrados en Inventario para este lote.
    parent_lot_ids: tuple[str, ...] = field(default_factory=tuple)


_PRODUCIDOS = (
    "SELECT r.output_lot_id, p.name, r.output_type, r.actual_weight, r.created_at,"
    " r.processing_order_id, o.process_type"
    " FROM processing_output_results r"
    " JOIN processing_orders o ON o.id = r.processing_order_id"
    " LEFT JOIN products p ON p.id = r.product_id"
    " WHERE o.branch_id = ? AND r.output_lot_id IS NOT NULL AND r.output_lot_id <> ''"
)


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


class MeatLotTraceabilityQueryService:
    def __init__(self, connection, *, traceability_factory=None,
                 genealogy_factory=None) -> None:
        self._conn = connection
        if traceability_factory is None:
            from backend.application.inventory.queries import TraceabilityQueryService

            traceability_factory = TraceabilityQueryService
        self._traceability_factory = traceability_factory
        if genealogy_factory is None:
            from backend.application.meat_processing.queries import (
                ProcessGenealogyQueryService,
            )

            genealogy_factory = ProcessGenealogyQueryService
        self._genealogy_factory = genealogy_factory

    def search_lots(self, branch_id: str, *, query: str = "",
                    limit: int = 50) -> list[ProducedLot]:
        """Lotes producidos por la sucursal, el más reciente primero."""
        sql, valores = _PRODUCIDOS, [branch_id]
        if query:
            sql += " AND (r.output_lot_id LIKE ? OR p.name LIKE ?)"
            valores += [f"%{query}%"] * 2
        sql += " ORDER BY r.created_at DESC, r.id DESC LIMIT ?"
        return [_lote(fila) for fila in self._conn.execute(sql, [*valores, limit]).fetchall()]

    def trace(self, branch_id: str, lot_id: str) -> MeatLotTrace | None:
        """El recorrido del lote, o `None` si no lo produjo esta sucursal."""
        fila = self._conn.execute(
            _PRODUCIDOS + " AND r.output_lot_id = ? LIMIT 1", (branch_id, lot_id)).fetchone()
        if fila is None:
            return None
        producido = _lote(fila)
        trazabilidad = self._traceability_factory(self._conn)
        retiro = trazabilidad.recall_report(lot_id)
        aguas_arriba = trazabilidad.trace_upstream(lot_id)
        return MeatLotTrace(
            produced=producido,
            inputs=tuple(self._entradas(producido.processing_order_id)),
            chained=tuple(self._encadenados(lot_id)),
            destinations=tuple(
                LotDestination(
                    occurred_at=_texto(evento.occurred_at),
                    movement_type=_texto(evento.movement_type),
                    source_module=_texto(evento.source_module),
                    source_document_type=_texto(evento.source_document_type),
                    source_document_id=_texto(evento.source_document_id),
                    branch_id=_texto(evento.branch_id),
                    quantity=_texto(evento.quantity), weight=_texto(evento.weight))
                for evento in retiro.distribution),
            affected_lots=tuple(retiro.affected_lot_ids),
            reaches_customers=retiro.reaches_customers,
            branches_touched=tuple(retiro.branches_touched),
            parent_lot_ids=tuple(enlace.parent_lot_id for enlace in aguas_arriba.links),
        )

    def _encadenados(self, lot_id: str) -> list[ChainedConsumption]:
        """Órdenes que consumieron el lote, por el grafo de Cárnico.

        `ProcessGenealogyQueryService` (PROC-18) guarda la arista
        `ProcessOutput → MaterialConsumption` que deja el encadenamiento entre
        órdenes; aquí se resuelve a qué ORDEN pertenece ese consumo, que es lo
        que el operador reconoce. El grafo es polimórfico a propósito, así que
        la ORDEN la decide la búsqueda del consumo, no el tipo declarado en el
        enlace: lo que no es un consumo no aparece, en vez de inventarle una
        orden. Una misma arista alcanzada dos veces se cuenta una.
        """
        enlaces = self._genealogy_factory(self._conn).trace_lot_downstream(lot_id)
        vistos, salida = set(), []
        for enlace in enlaces:
            if enlace.downstream_entity_id in vistos:
                continue
            vistos.add(enlace.downstream_entity_id)
            fila = self._conn.execute(
                "SELECT c.processing_order_id, o.process_type, p.name"
                " FROM material_consumptions c"
                " JOIN processing_orders o ON o.id = c.processing_order_id"
                " LEFT JOIN products p ON p.id = c.product_id"
                " WHERE c.id = ?", (enlace.downstream_entity_id,)).fetchone()
            if fila is None:
                continue
            salida.append(ChainedConsumption(
                processing_order_id=_texto(fila[0]), process_type=_texto(fila[1]),
                product_name=_texto(fila[2]), quantity=_texto(enlace.quantity),
                weight=_texto(enlace.weight), linked_at=_texto(enlace.linked_at)))
        return salida

    def _entradas(self, processing_order_id: str) -> list[LotInput]:
        filas = self._conn.execute(
            "SELECT DISTINCT r.input_lot_id, ip.name, r.input_weight"
            " FROM processing_output_results r"
            " LEFT JOIN products ip ON ip.id = r.input_product_id"
            " WHERE r.processing_order_id = ?"
            "   AND r.input_lot_id IS NOT NULL AND r.input_lot_id <> ''"
            " ORDER BY ip.name, r.input_lot_id", (processing_order_id,)).fetchall()
        return [LotInput(lot_id=_texto(f[0]), product_name=_texto(f[1]), weight=_texto(f[2]))
                for f in filas]


def _lote(fila: Any) -> ProducedLot:
    return ProducedLot(
        lot_id=_texto(fila[0]), product_name=_texto(fila[1]), output_type=_texto(fila[2]),
        weight=_texto(fila[3]), produced_at=_texto(fila[4]),
        processing_order_id=_texto(fila[5]), process_type=_texto(fila[6]))
