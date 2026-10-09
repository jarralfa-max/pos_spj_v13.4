"""Tablero Kanban del pipeline (§21, CRM-43).

Una columna por etapa ACTIVA del catálogo (nunca etapas fijas en código).
Arrastrar una tarjeta a otra columna NO mueve la oportunidad: emite
``move_requested(opportunity_id, stage_id)`` y la página abre el formulario
de cambio de etapa, que invoca ``MoveOpportunityStageUseCase`` con sus
validaciones (permiso, campos obligatorios, actividades mínimas, motivo,
probabilidad, fecha). Si el caso de uso rechaza, la tarjeta se queda donde
estaba.

Accesible sin ratón: cada columna es una lista navegable con teclado y la
página ofrece «Mover etapa» sobre la tarjeta seleccionada.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import SectionCard
from frontend.desktop.themes.tokens import Spacing

_ROLE_ID = Qt.UserRole


@dataclass(frozen=True)
class KanbanCard:
    card_id: str
    title: str
    lines: tuple[str, ...]
    tooltip: str = ""


@dataclass(frozen=True)
class KanbanColumn:
    column_id: str
    title: str
    summary: str
    cards: tuple[KanbanCard, ...]


class _StageList(QListWidget):
    dropped = pyqtSignal(str, str)  # card_id, target column_id

    def __init__(self, column_id: str, parent=None) -> None:
        super().__init__(parent)
        self.column_id = column_id
        self.setObjectName("crmKanbanColumnList")
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setWordWrap(True)
        self.setSpacing(Spacing.XS)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def dropEvent(self, event):  # noqa: N802 — Qt override
        source = event.source()
        if isinstance(source, _StageList) and source is not self:
            item = source.currentItem()
            if item is not None:
                self.dropped.emit(str(item.data(_ROLE_ID)), self.column_id)
        # Nunca se acepta el movimiento visual: lo decide el caso de uso.
        event.ignore()


class KanbanBoard(QScrollArea):
    move_requested = pyqtSignal(str, str)
    card_opened = pyqtSignal(str)
    selection_changed = pyqtSignal(object)  # card_id | None

    COLUMN_WIDTH = 280

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("crmKanbanBoard")
        self.setAccessibleName("Tablero del pipeline")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._host = QWidget(self)
        self._row = QHBoxLayout(self._host)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(Spacing.MD)
        self.setWidget(self._host)
        self._lists: list[_StageList] = []

    def set_columns(self, columns: list[KanbanColumn]) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._lists = []
        for column in columns:
            card = SectionCard(self._host, title=column.title)
            card.setMinimumWidth(self.COLUMN_WIDTH)
            card.setMaximumWidth(self.COLUMN_WIDTH + 40)
            card.setAccessibleName(f"Etapa {column.title}")
            summary = QLabel(column.summary, card)
            summary.setProperty("role", "muted")
            summary.setWordWrap(True)
            card.add(summary)
            stage_list = _StageList(column.column_id, card)
            stage_list.setAccessibleName(f"Oportunidades en {column.title}")
            for kanban_card in column.cards:
                text = "\n".join((kanban_card.title, *kanban_card.lines))
                item = QListWidgetItem(text)
                item.setData(_ROLE_ID, kanban_card.card_id)
                item.setToolTip(kanban_card.tooltip or text)
                stage_list.addItem(item)
            if not column.cards:
                empty = QListWidgetItem("Sin oportunidades")
                empty.setFlags(Qt.NoItemFlags)
                stage_list.addItem(empty)
            stage_list.dropped.connect(self.move_requested.emit)
            stage_list.itemDoubleClicked.connect(
                lambda item: item.data(_ROLE_ID) and self.card_opened.emit(item.data(_ROLE_ID)))
            stage_list.currentItemChanged.connect(
                lambda current, _prev, lst=stage_list: self._on_current(lst, current))
            card.add(stage_list)
            self._lists.append(stage_list)
            self._row.addWidget(card)
        self._row.addStretch(1)

    def _on_current(self, owner: _StageList, current) -> None:
        if current is None:
            return
        for other in self._lists:
            if other is not owner:
                other.blockSignals(True)
                other.clearSelection()
                other.setCurrentRow(-1)
                other.blockSignals(False)
        self.selection_changed.emit(current.data(_ROLE_ID))

    def selected_card_id(self) -> str | None:
        for stage_list in self._lists:
            item = stage_list.currentItem()
            if item is not None and item.isSelected() and item.data(_ROLE_ID):
                return str(item.data(_ROLE_ID))
        return None
