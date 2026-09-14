"""MeatProcessingBadgeQueryService — contadores del sidebar de Procesamiento Cárnico.

Antes no existía: el sidebar declaraba seis claves de badge y la vista se armaba
con `badges={}`. Cada contador aquí es el "por atender" de su registro
(`MeatProcessingRecordsQueryService.count_needing_attention`), con la misma
definición que ordena esa lista: el número y la pantalla no pueden divergir.

`orders_needing_attention` cuenta órdenes esperando a alguien (aprobación,
materiales, calidad o conciliación). `critical_alerts` no se calcula: las alertas
de producción sólo quedan en la auditoría y no tienen estado de "atendida".
"""

from __future__ import annotations

from backend.application.meat_processing.queries.meat_processing_records_query_service import (
    MeatProcessingRecord,
    MeatProcessingRecordsQueryService,
)
from backend.domain.meat_processing.enums import ProcessingOrderStatus

#: Órdenes que esperan una decisión o un insumo, no a que termine el trabajo.
ORDERS_NEEDING_ATTENTION = (
    ProcessingOrderStatus.PENDING_APPROVAL, ProcessingOrderStatus.MATERIALS_PENDING,
    ProcessingOrderStatus.PENDING_QUALITY, ProcessingOrderStatus.PENDING_RECONCILIATION,
)

#: Clave del sidebar → registro cuyo "por atender" cuenta.
BADGE_RECORDS = {
    "active_orders": MeatProcessingRecord.ACTIVE_PROCESSING,
    "yield_out_of_tolerance": MeatProcessingRecord.YIELDS,
    "pending_quality": MeatProcessingRecord.QUALITY,
    "open_incidents": MeatProcessingRecord.INCIDENTS,
}


class MeatProcessingBadgeQueryService:
    def __init__(self, db) -> None:
        self.db = db

    def get_badge_counts(self, branch_id: str) -> dict[str, int]:
        registros = MeatProcessingRecordsQueryService(self.db)
        counts = {clave: registros.count_needing_attention(branch_id, record)
                  for clave, record in BADGE_RECORDS.items()}
        marcas = ",".join("?" for _ in ORDERS_NEEDING_ATTENTION)
        counts["orders_needing_attention"] = self.db.execute(
            f"SELECT COUNT(*) FROM processing_orders WHERE branch_id=? AND status IN ({marcas})",
            (branch_id, *(s.value for s in ORDERS_NEEDING_ATTENTION))).fetchone()[0]
        return counts
