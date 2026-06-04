"""Address autocomplete input backed by GeocodingService.

Uses Mapbox through GeocodingService as primary provider and Nominatim as fallback.
All autocomplete calls run in QRunnable workers via QThreadPool; the widget never
performs HTTP work on the Qt main thread.
"""
from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QLineEdit, QListWidget, QListWidgetItem, QTextEdit, QVBoxLayout, QWidget

from core.services.geocoding_service import GeocodingService


class _AddressLookupSignals(QObject):
    finished = pyqtSignal(int, list)
    failed = pyqtSignal(int, str)


class _AddressLookupTask(QRunnable):
    def __init__(self, request_id: int, service: GeocodingService, query: str, limit: int) -> None:
        super().__init__()
        self.request_id = request_id
        self.service = service
        self.query = query
        self.limit = limit
        self.signals = _AddressLookupSignals()

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.request_id, self.service.autocomplete(self.query, self.limit))
        except Exception as exc:  # defensive boundary for Qt worker
            self.signals.failed.emit(self.request_id, str(exc))


class AddressAutocompleteInput(QWidget):
    """Search + manual address input with async geocoding autocomplete."""

    selected = pyqtSignal(dict)

    def __init__(
        self,
        parent=None,
        *,
        geocoding_service: GeocodingService | None = None,
        debounce_ms: int = 350,
        limit: int = 5,
    ) -> None:
        super().__init__(parent)
        self._service = geocoding_service or GeocodingService()
        self._thread_pool = QThreadPool.globalInstance()
        self._request_id = 0
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._limit = limit

        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("Buscar dirección en mapa...")
        self._manual_toggle = QCheckBox("Captura manual", self)
        self._manual_text = QTextEdit(self)
        self._manual_text.setPlaceholderText("Escribe la dirección manualmente")
        self._suggestions = QListWidget(self)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._start_lookup)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._suggestions)
        layout.addWidget(self._manual_toggle)
        layout.addWidget(self._manual_text)

        self._manual_text.setVisible(False)
        self._manual_toggle.toggled.connect(self._manual_text.setVisible)
        self._search_box.textChanged.connect(lambda _text: self._debounce.start())
        self._suggestions.itemActivated.connect(self._emit_selected)

    def value(self) -> str:
        if self._manual_toggle.isChecked():
            return self._manual_text.toPlainText().strip()
        item = self._suggestions.currentItem()
        return self._search_box.text().strip() if item is None else item.text()

    def set_manual_value(self, value: str) -> None:
        self._manual_toggle.setChecked(True)
        self._manual_text.setPlainText((value or "").strip())
        self._search_box.setText((value or "").strip())

    def _start_lookup(self) -> None:
        query = self._search_box.text().strip()
        if not query:
            self._suggestions.clear()
            return
        cache_key = query.lower()
        if cache_key in self._cache:
            self._populate(self._cache[cache_key])
            return
        self._request_id += 1
        task = _AddressLookupTask(self._request_id, self._service, query, self._limit)
        task.signals.finished.connect(self._handle_results)
        task.signals.failed.connect(self._handle_failure)
        self._thread_pool.start(task)

    def _handle_results(self, request_id: int, results: list) -> None:
        if request_id != self._request_id:
            return
        normalized = [dict(result) for result in results]
        self._cache[self._search_box.text().strip().lower()] = normalized
        self._populate(normalized)

    def _handle_failure(self, request_id: int, _message: str) -> None:
        if request_id == self._request_id:
            self._suggestions.clear()

    def _populate(self, results: list[dict[str, Any]]) -> None:
        self._suggestions.clear()
        for result in results:
            label = str(result.get("label") or result.get("place_name") or "").strip()
            if not label:
                continue
            item = QListWidgetItem(label)
            item.setData(32, result)
            self._suggestions.addItem(item)

    def _emit_selected(self, item: QListWidgetItem) -> None:
        self.selected.emit(item.data(32) or {"label": item.text()})
