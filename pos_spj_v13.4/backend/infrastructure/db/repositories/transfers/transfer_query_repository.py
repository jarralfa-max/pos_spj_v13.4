"""Read-only canonical Transfers workspace projection."""
from backend.application.transfers.queries.workspace_query_service import (
    TransferKPIViewModel, TransferPageViewModel, TransferRowViewModel,
)


_STATUS_BY_PAGE = {
    "transfers_requests": ("DRAFT", "PENDING_APPROVAL"),
    "transfers_approvals": ("PENDING_APPROVAL",),
    "transfers_picking": ("RESERVED", "PICKING", "PARTIALLY_PICKED"),
    "transfers_ready_to_dispatch": ("PICKED", "READY_TO_DISPATCH"),
    "transfers_in_transit": ("PARTIALLY_DISPATCHED", "IN_TRANSIT"),
    "transfers_receipts": ("IN_TRANSIT", "PARTIALLY_RECEIVED", "RECEIVED"),
    "transfers_differences": ("WITH_DIFFERENCES", "PENDING_RESOLUTION"),
    "transfers_returns": ("RETURN_IN_PROGRESS",),
}


class TransferWorkspaceQueryRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def page(self, *, page_id: str, search: str = "") -> TransferPageViewModel:
        statuses = _STATUS_BY_PAGE.get(page_id, ())
        where, params = [], []
        if statuses:
            where.append("status IN ({})".format(",".join("?" for _ in statuses)))
            params.extend(statuses)
        if search.strip():
            where.append("(transfer_number LIKE ? OR origin_branch_id LIKE ? OR destination_branch_id LIKE ?)")
            params.extend([f"%{search.strip()}%"] * 3)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._db.execute(
            f"SELECT id, transfer_number, COALESCE(origin_branch_id, origin_warehouse_id, origin_location_id, origin_node_type), COALESCE(destination_branch_id, destination_warehouse_id, destination_location_id, destination_node_type), status, updated_at FROM stock_transfers {clause} ORDER BY updated_at DESC LIMIT 500",
            params).fetchall()
        view_rows = tuple(TransferRowViewModel(*map(str, row)) for row in rows)
        kpis = self._kpis() if page_id == "transfers_overview" else ()
        return TransferPageViewModel(rows=view_rows, kpis=kpis)

    def _kpis(self) -> tuple[TransferKPIViewModel, ...]:
        groups = (
            ("Solicitudes pendientes", ("DRAFT", "PENDING_APPROVAL"), "warning"),
            ("Pendientes de aprobación", ("PENDING_APPROVAL",), "warning"),
            ("Listas para despacho", ("PICKED", "READY_TO_DISPATCH"), "info"),
            ("En tránsito", ("PARTIALLY_DISPATCHED", "IN_TRANSIT"), "info"),
            ("Recepciones pendientes", ("IN_TRANSIT", "PARTIALLY_RECEIVED"), "warning"),
            ("Diferencias abiertas", ("WITH_DIFFERENCES", "PENDING_RESOLUTION"), "danger"),
        )
        result = []
        for title, statuses, variant in groups:
            marks = ",".join("?" for _ in statuses)
            count = self._db.execute(
                f"SELECT COUNT(*) FROM stock_transfers WHERE status IN ({marks})",
                statuses).fetchone()[0]
            result.append(TransferKPIViewModel(title, str(count), variant))
        return tuple(result)
