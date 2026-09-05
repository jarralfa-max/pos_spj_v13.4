"""WorkOrdersBoardPage (ASSET-19, route ``assets.maintenance.work_orders``) —
read-only board of open maintenance work orders grouped by status.

**This is explicitly a READ-ONLY preview, not the interactive Kanban §95
describes** ("Mover tarjeta debe invocar UseCase"). No
`StartMaintenanceWorkOrderUseCase`/`CompleteMaintenanceWorkOrderUseCase`/etc.
exists yet (ASSET-6 built the domain entity's guarded state machine, but no
application-layer use case wraps it — see
``docs/refactor/ASSET-18_directorio_detalle.md``'s "Siguiente fase"), so
there is nothing a drag-and-drop action could actually call. Building fake
drag handlers that don't mutate anything would be worse than an honest
static board — this page says so in its own header subtitle, not just in a
code comment nobody using the app would see.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.domain.assets.enums import MaintenanceWorkOrderStatus
from frontend.desktop.components import PageHeader, ViewState, create_state_widget
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_COLUMN_ORDER = (
    MaintenanceWorkOrderStatus.REQUESTED, MaintenanceWorkOrderStatus.APPROVED,
    MaintenanceWorkOrderStatus.SCHEDULED, MaintenanceWorkOrderStatus.ASSIGNED,
    MaintenanceWorkOrderStatus.IN_PROGRESS, MaintenanceWorkOrderStatus.PAUSED,
    MaintenanceWorkOrderStatus.WAITING_PARTS, MaintenanceWorkOrderStatus.WAITING_PROVIDER,
    MaintenanceWorkOrderStatus.COMPLETED,
)
_COLUMN_LABELS = {
    MaintenanceWorkOrderStatus.REQUESTED: "Solicitadas",
    MaintenanceWorkOrderStatus.APPROVED: "Aprobadas",
    MaintenanceWorkOrderStatus.SCHEDULED: "Programadas",
    MaintenanceWorkOrderStatus.ASSIGNED: "Asignadas",
    MaintenanceWorkOrderStatus.IN_PROGRESS: "En progreso",
    MaintenanceWorkOrderStatus.PAUSED: "Pausadas",
    MaintenanceWorkOrderStatus.WAITING_PARTS: "Esperando refacciones",
    MaintenanceWorkOrderStatus.WAITING_PROVIDER: "Esperando proveedor",
    MaintenanceWorkOrderStatus.COMPLETED: "Completadas",
}


class _WorkOrderCard(QFrame):
    def __init__(self, work_order, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetsWorkOrderCard")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(2)
        number = QLabel(work_order.work_order_number, self)
        number.setAccessibleName(f"Orden de trabajo {work_order.work_order_number}")
        layout.addWidget(number)
        priority = QLabel(f"Prioridad: {work_order.priority.value}", self)
        layout.addWidget(priority)
        if work_order.scheduled_at:
            layout.addWidget(QLabel(f"Programada: {work_order.scheduled_at}", self))


class _BoardColumn(QFrame):
    def __init__(self, status: MaintenanceWorkOrderStatus, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("assetsWorkOrderColumn")
        self.setAccessibleName(_COLUMN_LABELS[status])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        self._title = QLabel(_COLUMN_LABELS[status], self)
        layout.addWidget(self._title)
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(Spacing.SM)
        layout.addLayout(self._cards_layout)
        layout.addStretch(1)

    def set_work_orders(self, work_orders: list) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for wo in work_orders:
            self._cards_layout.addWidget(_WorkOrderCard(wo, self))


class WorkOrdersBoardPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("workOrdersBoardPage")
        self._presenter = presenter
        self._loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title="Órdenes de trabajo",
            subtitle="Vista de solo lectura — mover una orden entre columnas no está "
                     "disponible todavía (requiere casos de uso de mutación aún no construidos).",
            icon=Icons.MAINTENANCE, compact=True))

        self._status = QLabel("", self)
        self._status.setObjectName("workOrdersBoardStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        self._empty = create_state_widget(
            ViewState.EMPTY, self, message="No hay órdenes de trabajo abiertas")
        root.addWidget(self._empty)
        self._empty.hide()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        board_host = QWidget(scroll)
        self._board = QHBoxLayout(board_host)
        self._board.setSpacing(Spacing.SM)
        self._columns: dict[MaintenanceWorkOrderStatus, _BoardColumn] = {}
        for status in _COLUMN_ORDER:
            column = _BoardColumn(status, board_host)
            self._columns[status] = column
            self._board.addWidget(column, stretch=1)
        scroll.setWidget(board_host)
        root.addWidget(scroll, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            work_orders = self._presenter.work_orders()
            by_status: dict[MaintenanceWorkOrderStatus, list] = {s: [] for s in _COLUMN_ORDER}
            for wo in work_orders:
                status = MaintenanceWorkOrderStatus(wo.status)
                by_status.setdefault(status, []).append(wo)
            for status, column in self._columns.items():
                column.set_work_orders(by_status.get(status, []))
            self._empty.setVisible(not work_orders)
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setText(f"No fue posible cargar las órdenes de trabajo: {exc}")
            self._status.show()
