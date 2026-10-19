"""Reusable autocomplete selector for entities."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Iterable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class SearchOption:
    id: str
    label: str
    subtitle: str = ""
    tooltip: str = ""


SearchProvider = Callable[[str], Iterable[SearchOption]]

logger = logging.getLogger("spj.search_selector")


#: Mensaje mostrado cuando el provider lanza una excepción — distinto a "sin
#: resultados" a propósito (§35 del master prompt: no presentar un fallo
#: técnico como si fueran cero coincidencias).
SEARCH_FAILED_MESSAGE = "No se pudo consultar. Intente de nuevo."
NO_RESULTS_MESSAGE = "Sin resultados."


class SearchSelector(QWidget):
    selected = pyqtSignal(object)
    #: Emitida SOLO cuando el provider lanza (no cuando simplemente no hay
    #: coincidencias). El mensaje es apto para mostrar al usuario.
    search_failed = pyqtSignal(str)
    #: El usuario escribió o borró en la caja (no se emite al fijar la etiqueta
    #: de lo elegido). Quien guarda una selección debe invalidarla aquí
    #: (auditoría CRM F13: el id anterior seguía elegido con otro texto escrito).
    text_edited = pyqtSignal(str)
    #: Intro sin opción elegible: el texto tal cual (p. ej. lo que teclea un
    #: lector de código QR/barras, que no coincide con ninguna búsqueda).
    submitted = pyqtSignal(str)

    def __init__(self, parent=None, *, provider: SearchProvider | None = None,
                 placeholder: str = "Buscar...",
                 empty_reason_provider: Callable[[str], str | None] | None = None,
                 collapse_when_empty: bool = False, keep_selection: bool = False) -> None:
        super().__init__(parent)
        #: Auditoría de Producción 32cfbf P0 (2026-10-16): `selected_option()`
        #: depende del renglón resaltado y cualquier búsqueda nueva lo borra, así
        #: que un diálogo que lo lee al cerrarse pierde lo elegido. Con
        #: `keep_selection` el selector RETIENE la opción emitida (clic o Intro),
        #: muestra su etiqueta y la invalida cuando el usuario vuelve a escribir.
        #: Opcional para no cambiar a los consumidores que guardan la suya.
        self._keep_selection = keep_selection
        self._picked: SearchOption | None = None
        #: Oculta la lista mientras no tenga renglones (para paneles con poco
        #: alto, como el cliente del POS): sin esto la lista vacía ocupa su
        #: altura mínima aunque no haya nada que elegir.
        self._collapse_when_empty = collapse_when_empty
        self._provider = provider or (lambda _query: [])
        #: Explica POR QUÉ no hubo resultados (catálogo vacío, nada habilitado
        #: en esta sucursal, sólo borradores…). Sin él se mantiene el mensaje
        #: genérico de siempre.
        self._empty_reason_provider = empty_reason_provider
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText(placeholder)
        self._results = QListWidget(self)
        self._options: list[SearchOption] = []
        self._search_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._results)

        self._search_box.textChanged.connect(self.refresh)
        self._search_box.textChanged.connect(self._forget_pick)
        self._search_box.textChanged.connect(self.text_edited.emit)
        self._search_box.returnPressed.connect(self._emit_current_selected)
        self._results.itemClicked.connect(self._emit_selected)
        self._sync_results_visibility()

    def _sync_results_visibility(self) -> None:
        if self._collapse_when_empty:
            self._results.setVisible(self._results.count() > 0)

    def set_provider(self, provider: SearchProvider) -> None:
        self._provider = provider
        self.refresh(self._search_box.text())

    def set_empty_reason_provider(
            self, provider: Callable[[str], str | None] | None) -> None:
        self._empty_reason_provider = provider

    def _empty_message(self, query: str) -> str:
        """Cero resultados tiene causas distintas y decirlas ahorra el "está
        roto". Es un diagnóstico: si falla, se cae al mensaje genérico — nunca
        rompe el buscador."""
        if self._empty_reason_provider is None:
            return NO_RESULTS_MESSAGE
        try:
            reason = self._empty_reason_provider(query)
        except Exception:
            logger.exception("empty-reason provider failed (len=%s)", len(query))
            return NO_RESULTS_MESSAGE
        return reason or NO_RESULTS_MESSAGE

    def refresh(self, query: str | None = None) -> None:
        query_text = self._search_box.text() if query is None else query
        try:
            self._options = list(self._provider(query_text.strip()))
            self._search_failed = False
        except Exception:
            logger.exception("SearchSelector provider failed (len=%s)", len(query_text))
            self._options = []
            self._search_failed = True
        self._results.clear()
        try:
            if self._search_failed:
                self._add_status_row(SEARCH_FAILED_MESSAGE)
                self.search_failed.emit(SEARCH_FAILED_MESSAGE)
                return
            if not self._options and query_text.strip():
                self._add_status_row(self._empty_message(query_text.strip()))
                return
            for option in self._options:
                text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, option)
                item.setData(32, option)  # legacy role kept for existing tests/callers
                self._results.addItem(item)
        finally:
            self._sync_results_visibility()

    def has_search_failed(self) -> bool:
        return self._search_failed

    def _add_status_row(self, text: str) -> None:
        """A non-selectable row: distinguishes '0 matches' / 'query failed'
        from a real, pickable option without changing the selection contract."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(Qt.gray)
        self._results.addItem(item)

    def selected_option(self) -> SearchOption | None:
        item = self._results.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole) or item.data(32)

    def set_text_silently(self, text: str) -> None:
        was_blocked = self._search_box.blockSignals(True)
        try:
            self._search_box.setText(text)
        finally:
            self._search_box.blockSignals(was_blocked)

    def clear_selection(self) -> None:
        self._results.clearSelection()
        self._results.setCurrentRow(-1)

    def clear_results(self) -> None:
        self._results.clear()
        self._options = []
        self._sync_results_visibility()

    def set_selected_label(self, text: str) -> None:
        self.set_text_silently(text)
        self.clear_results()

    def clear(self) -> None:
        self._search_box.clear()
        self.clear_results()
        self._picked = None

    def picked_option(self) -> SearchOption | None:
        """Lo que el usuario eligió (clic o Intro) y sigue vigente: no depende
        del renglón resaltado. Sólo con `keep_selection=True`."""
        return self._picked

    def set_picked(self, option: SearchOption | None) -> None:
        """Fija una selección ya conocida (precarga), mostrando su etiqueta."""
        self._picked = option
        if option is not None:
            self.set_selected_label(option.label)

    def _forget_pick(self, _text: str = "") -> None:
        self._picked = None

    def _emit_current_selected(self) -> None:
        item = self._results.currentItem()
        if item is None:
            # Intro sin renglón resaltado: si hay UNA sola opción elegible, es
            # ésa (antes Intro no hacía nada y el diálogo se aceptaba sin producto).
            elegibles = [self._results.item(i) for i in range(self._results.count())
                         if self._results.item(i).data(Qt.UserRole) is not None]
            item = elegibles[0] if len(elegibles) == 1 else None
        if item is not None:
            self._emit_selected(item)
        elif self._search_box.text().strip():
            self.submitted.emit(self._search_box.text().strip())

    def text(self) -> str:
        return self._search_box.text()

    def focus_search(self) -> None:
        self._search_box.setFocus()

    def _emit_selected(self, item: QListWidgetItem) -> None:
        option = item.data(Qt.UserRole) or item.data(32)
        if option is None:
            return
        if self._keep_selection:
            self._picked = option
            self.set_selected_label(option.label)
        self.selected.emit(option)
