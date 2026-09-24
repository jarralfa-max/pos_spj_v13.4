"""MeatProcessingOverviewQueryService — los indicadores del Resumen.

POR QUÉ NO UNA DEFINICIÓN PROPIA
-------------------------------
Los cinco contadores de "por atender" son EXACTAMENTE los del sidebar
(`MeatProcessingBadgeQueryService`), que a su vez son los "por atender" de cada
registro. Si el Resumen los volviera a calcular, la pantalla, el badge y la
lista podrían decir tres números distintos del mismo hecho.

Lo que el Resumen sí agrega es la foto del periodo: cuántas órdenes hay en cada
estado del ciclo de vida y cuánto peso salió por tipo de salida. Los pesos se
suman con `Decimal`, no con `SUM(CAST(... AS REAL))`: en este esquema los
decimales viven como TEXTO justamente para no perder precisión.

Ordenar por el enum no pierde filas: el `CHECK` del esquema ya restringe
`processing_orders.status` y `process_outputs.output_type` a ese mismo
vocabulario, así que aquí no se revalida lo que la base ya garantiza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.queries.meat_processing_badge_query_service import (
    MeatProcessingBadgeQueryService,
)
from backend.domain.meat_processing.enums import OutputType, ProcessingOrderStatus

#: Orden del ciclo de vida: el Resumen lo lee así, no alfabéticamente.
STATUS_ORDER: tuple[str, ...] = tuple(estado.value for estado in ProcessingOrderStatus)
OUTPUT_ORDER: tuple[str, ...] = tuple(tipo.value for tipo in OutputType)

DEFAULT_DAYS = 7


@dataclass(frozen=True, slots=True)
class StatusCount:
    status: str
    count: int


@dataclass(frozen=True, slots=True)
class OutputTotal:
    output_type: str
    outputs: int
    weight: str
    quantity: str


@dataclass(frozen=True, slots=True)
class MeatProcessingOverview:
    """Lo que el Resumen enseña. `attention` son los mismos contadores del sidebar."""

    attention: dict[str, int]
    by_status: tuple[StatusCount, ...]
    production: tuple[OutputTotal, ...]
    days: int
    since: str


def _decimal(valor) -> Decimal:
    try:
        return Decimal(str(valor or "0"))
    except InvalidOperation:
        return Decimal("0")


def _texto(valor: Decimal) -> str:
    return f"{valor.normalize():f}" if valor else "0"


class MeatProcessingOverviewQueryService:
    def __init__(self, connection, *, badge_factory=MeatProcessingBadgeQueryService) -> None:
        self._conn = connection
        self._badge_factory = badge_factory

    def overview(self, branch_id: str, *, days: int = DEFAULT_DAYS,
                 now: datetime | None = None) -> MeatProcessingOverview:
        if days <= 0:
            raise ValueError("El periodo del resumen debe ser de al menos un día")
        desde = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).isoformat()
        return MeatProcessingOverview(
            attention=self._badge_factory(self._conn).get_badge_counts(branch_id),
            by_status=self._por_estado(branch_id),
            production=self._produccion(branch_id, desde),
            days=days, since=desde)

    def _por_estado(self, branch_id: str) -> tuple[StatusCount, ...]:
        filas = self._conn.execute(
            "SELECT status, COUNT(*) FROM processing_orders WHERE branch_id=? GROUP BY status",
            (branch_id,)).fetchall()
        conteos = {estado: cuantas for estado, cuantas in filas}
        return tuple(StatusCount(status=estado, count=conteos[estado])
                     for estado in STATUS_ORDER if estado in conteos)

    def _produccion(self, branch_id: str, desde: str) -> tuple[OutputTotal, ...]:
        filas = self._conn.execute(
            "SELECT s.output_type, s.quantity, s.weight FROM process_outputs s"
            " JOIN processing_orders o ON o.id = s.processing_order_id"
            " WHERE o.branch_id = ? AND s.produced_at >= ?", (branch_id, desde)).fetchall()
        acumulado: dict[str, list] = {}
        for tipo, cantidad, peso in filas:
            total = acumulado.setdefault(tipo, [0, Decimal("0"), Decimal("0")])
            total[0] += 1
            total[1] += _decimal(peso)
            total[2] += _decimal(cantidad)
        return tuple(
            OutputTotal(output_type=tipo, outputs=acumulado[tipo][0],
                        weight=_texto(acumulado[tipo][1]),
                        quantity=_texto(acumulado[tipo][2]))
            for tipo in OUTPUT_ORDER if tipo in acumulado)
