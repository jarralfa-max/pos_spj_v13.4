"""EntitySearchInput (FASE DS-4) — search + select for large entities by UUID.

For products, customers, suppliers, employees, lots, orders… A debounced
SearchInput drives a paginated provider (a QueryService callback returning
``SearchOption`` rows); the user selects one and the widget emits its UUID.
Never loads thousands of rows into a QComboBox.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.search_selector import (
    NO_RESULTS_MESSAGE,
    SEARCH_FAILED_MESSAGE,
    SearchOption,
)
from frontend.desktop.themes.tokens import Spacing

logger = logging.getLogger("spj.entity_search_input")

Provider = Callable[[str], Iterable[SearchOption]]


class EntitySearchInput(QWidget):
    selected = pyqtSignal(object)   # emits the chosen entity id (UUID str)
    #: Emitida SOLO cuando el provider lanza (no cuando simplemente no hay
    #: coincidencias). El mensaje es apto para mostrar al usuario.
    search_failed = pyqtSignal(str)

    def __init__(self, parent=None, *, provider: Provider | None = None,
                 placeholder: str = "Buscar por nombre, código o teléfono",
                 max_results: int = 25, debounce_ms: int = 300,
                 empty_reason_provider: Callable[[str], str | None] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("entitySearchInput")
        self._provider = provider or (lambda _q: [])
        #: Ver `SearchSelector`: explica por qué no hubo resultados.
        self._empty_reason_provider = empty_reason_provider
        self._max_results = max_results
        self._selected_id = None
        self._selected_label = ""
        self._search_failed = False

        self._search = SearchInput(self, placeholder=placeholder, debounce_ms=debounce_ms)
        self._results = QListWidget(self)
        self._results.setObjectName("entitySearchResults")
        self._results.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XXS)
        layout.addWidget(self._search)
        layout.addWidget(self._results)

        self._search.search_changed.connect(self._run_search)
        self._results.itemClicked.connect(self._choose)
        # Teclado. Sólo se podía elegir con CLIC, y dentro de un diálogo Enter
        # activaba "Aceptar": escribir un producto y pulsar Enter CERRABA el
        # diálogo sin líneas y se perdía todo lo capturado (reproducido el
        # 2026-09-18 en "Nueva solicitud de compra"). El filtro va aquí y no en
        # `SearchInput` porque éste también filtra listados, donde Enter tiene
        # otro significado.
        self._search.installEventFilter(self)
        # Editar el texto después de elegir invalida la selección: si no, el
        # texto dice una cosa y `selected_id()` devuelve otra, y "Agregar"
        # añadía el producto anterior. `textEdited` sólo lo emite el usuario.
        self._search.textEdited.connect(self._on_user_edit)

    def set_provider(self, provider: Provider) -> None:
        self._provider = provider

    def set_empty_reason_provider(
            self, provider: Callable[[str], str | None] | None) -> None:
        self._empty_reason_provider = provider

    def _empty_message(self, query: str) -> str:
        """Diagnóstico, no camino crítico: si falla, mensaje genérico."""
        if self._empty_reason_provider is None:
            return NO_RESULTS_MESSAGE
        try:
            reason = self._empty_reason_provider(query)
        except Exception:
            logger.exception("empty-reason provider failed query=%r", query)
            return NO_RESULTS_MESSAGE
        return reason or NO_RESULTS_MESSAGE

    def selected_id(self):
        return self._selected_id

    def selected_label(self) -> str:
        return self._selected_label

    def set_selected_label(self, entity_id, label: str) -> None:
        self._selected_id = entity_id
        self._selected_label = str(label or "")
        self._search.blockSignals(True)
        self._search.setText(label)
        self._search.blockSignals(False)
        self._results.setVisible(False)

    def clear(self) -> None:
        self._selected_id = None
        self._selected_label = ""
        self._search.clear()
        self._results.clear()
        self._results.setVisible(False)

    def has_search_failed(self) -> bool:
        return self._search_failed

    def _run_search(self, query: str) -> None:
        self._results.clear()
        if not query:
            self._results.setVisible(False)
            self._search_failed = False
            return
        try:
            options = list(self._provider(query))[: self._max_results]
            self._search_failed = False
        except Exception:
            logger.exception("EntitySearchInput provider failed query=%r", query)
            options = []
            self._search_failed = True
        if self._search_failed:
            self._add_status_row(SEARCH_FAILED_MESSAGE)
            self._results.setVisible(True)
            self.search_failed.emit(SEARCH_FAILED_MESSAGE)
            return
        if not options:
            self._add_status_row(self._empty_message(query))
            self._results.setVisible(True)
            return
        for option in options:
            text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, option)
            self._results.addItem(item)
        self._results.setVisible(bool(options))
        # Resaltar el primero: así se VE qué va a elegir Enter.
        if options:
            self._results.setCurrentRow(0)

    # ── teclado ─────────────────────────────────────────────────────────
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - API de Qt
        if obj is self._search and event.type() == QEvent.KeyPress:
            tecla = event.key()
            if tecla in (Qt.Key_Down, Qt.Key_Up):
                self._move_highlight(1 if tecla == Qt.Key_Down else -1)
                return True
            if tecla in (Qt.Key_Return, Qt.Key_Enter):
                self._choose_highlighted()
                # SIEMPRE consumida: nunca debe llegar al diálogo.
                return True
            if tecla == Qt.Key_Escape and self._results.isVisible():
                self._results.setVisible(False)
                return True
        return super().eventFilter(obj, event)

    def _selectable_rows(self) -> list[int]:
        return [i for i in range(self._results.count())
                if self._results.item(i).data(Qt.UserRole) is not None]

    def _move_highlight(self, paso: int) -> None:
        filas = self._selectable_rows()
        if not filas:
            return
        self._results.setVisible(True)
        actual = self._results.currentRow()
        if actual not in filas:
            destino = filas[0] if paso > 0 else filas[-1]
        else:
            destino = filas[(filas.index(actual) + paso) % len(filas)]
        self._results.setCurrentRow(destino)

    def _choose_highlighted(self) -> None:
        """Enter elige el resultado resaltado. Si la búsqueda aún no corrió
        (se pulsó antes de que venciera la espera), se ejecuta ya."""
        texto = self._search.text().strip()
        if texto and texto != self._selected_label and not self._selectable_rows():
            self._run_search(texto)
        filas = self._selectable_rows()
        if not filas:
            return
        fila = self._results.currentRow()
        if fila not in filas:
            fila = filas[0]
        self._choose(self._results.item(fila))

    def _on_user_edit(self, texto: str) -> None:
        if self._selected_id is not None and texto != self._selected_label:
            self._selected_id = None
            self._selected_label = ""

    def _add_status_row(self, text: str) -> None:
        """A non-selectable row: distinguishes '0 matches' / 'query failed'
        from a real, pickable option without changing the selection contract."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(Qt.gray)
        self._results.addItem(item)

    def _choose(self, item: QListWidgetItem) -> None:
        option: SearchOption = item.data(Qt.UserRole)
        if option is None:
            return
        self._selected_id = option.id
        self._selected_label = option.label
        self._search.blockSignals(True)
        self._search.setText(option.label)
        self._search.blockSignals(False)
        self._results.setVisible(False)
        self.selected.emit(option.id)
