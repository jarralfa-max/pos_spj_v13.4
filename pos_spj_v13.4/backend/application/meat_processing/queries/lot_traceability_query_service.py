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
corte—, en qué orden se produjeron y qué lotes CONSUMIÓ esa orden (sus consumos
aplicados: todos los lotes de todos los insumos, no sólo el primero). Un lote que no
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
    #: Lo que la pantalla muestra: el código del lote, nunca su identidad.
    lot_code: str = ""
    order_folio: str = ""


@dataclass(frozen=True, slots=True)
class LotInput:
    """Lote de entrada que la orden consumió para producir el lote trazado."""

    lot_id: str
    product_name: str
    weight: str
    lot_code: str = ""


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
    branch_name: str = ""


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
    #: Cuándo se creó la orden (respaldo si una orden vieja no tiene folio).
    order_created_at: str = ""
    order_folio: str = ""


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
    " r.processing_order_id, o.process_type, l.lot_code, o.folio"
    " FROM processing_output_results r"
    " JOIN processing_orders o ON o.id = r.processing_order_id"
    " LEFT JOIN products p ON p.id = r.product_id"
    " LEFT JOIN inventory_lots l ON l.id = r.output_lot_id"
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
            sql += " AND (l.lot_code LIKE ? OR p.name LIKE ?)"
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
                    quantity=_texto(evento.quantity), weight=_texto(evento.weight),
                    branch_name=self._branch_name(evento.branch_id))
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
                "SELECT c.processing_order_id, o.process_type, p.name, o.created_at, o.folio"
                " FROM material_consumptions c"
                " JOIN processing_orders o ON o.id = c.processing_order_id"
                " LEFT JOIN products p ON p.id = c.product_id"
                " WHERE c.id = ?", (enlace.downstream_entity_id,)).fetchone()
            if fila is None:
                continue
            salida.append(ChainedConsumption(
                processing_order_id=_texto(fila[0]), process_type=_texto(fila[1]),
                product_name=_texto(fila[2]), quantity=_texto(enlace.quantity),
                weight=_texto(enlace.weight), linked_at=_texto(enlace.linked_at),
                order_created_at=_texto(fila[3]), order_folio=_texto(fila[4])))
        return salida

    def _branch_name(self, branch_id) -> str:
        """Nombre de la sucursal (catálogo de sucursales), o vacío si no está."""
        if not branch_id:
            return ""
        try:
            fila = self._conn.execute("SELECT nombre FROM sucursales WHERE id=?",
                                      (str(branch_id),)).fetchone()
        except Exception:  # noqa: BLE001 — base sin catálogo de sucursales
            return ""
        return _texto(fila[0]) if fila else ""

    def _entradas(self, processing_order_id: str) -> list[LotInput]:
        """Cada lote consumido por la orden, con lo que se consumió de él. Una
        formulación o un consumo repartido entre lotes tiene VARIOS padres."""
        from decimal import Decimal

        pesos: dict[tuple[str, str, str], Decimal] = {}
        for lote, nombre, peso, codigo in self._conn.execute(
                "SELECT c.lot_id, ip.name, c.actual_weight, l.lot_code"
                " FROM material_consumptions c"
                " LEFT JOIN products ip ON ip.id = c.product_id"
                " LEFT JOIN inventory_lots l ON l.id = c.lot_id"
                " WHERE c.processing_order_id = ? AND c.status = 'POSTED'"
                "   AND c.lot_id IS NOT NULL AND c.lot_id <> ''",
                (processing_order_id,)).fetchall():
            clave = (_texto(lote), _texto(nombre), _texto(codigo))
            pesos[clave] = pesos.get(clave, Decimal("0")) + Decimal(str(peso or 0))
        return [LotInput(lot_id=lote, product_name=nombre, weight=str(peso.normalize()),
                         lot_code=codigo)
                for (lote, nombre, codigo), peso in sorted(
                    pesos.items(), key=lambda e: (e[0][1], e[0][2], e[0][0]))]


def _lote(fila: Any) -> ProducedLot:
    return ProducedLot(
        lot_id=_texto(fila[0]), product_name=_texto(fila[1]), output_type=_texto(fila[2]),
        weight=_texto(fila[3]), produced_at=_texto(fila[4]),
        processing_order_id=_texto(fila[5]), process_type=_texto(fila[6]),
        lot_code=_texto(fila[7]), order_folio=_texto(fila[8]))
