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
        self._selected_result: dict[str, Any] | None = None
        self._address_verified = False
        self._selecting_suggestion = False

        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("Buscar dirección en mapa...")
        self._manual_toggle = QCheckBox("Captura manual", self)
        self._manual_text = QTextEdit(self)
        self._manual_text.setPlaceholderText("Escribe la dirección manualmente")
        self._suggestions = QListWidget(self)
        self._suggestions.setVisible(False)

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
        self._manual_toggle.toggled.connect(self._on_manual_toggled)
        self._search_box.textChanged.connect(self._on_text_changed)
        self._suggestions.itemClicked.connect(self._select_suggestion)
        self._suggestions.itemActivated.connect(self._select_suggestion)

    def value(self) -> str:
        if self._manual_toggle.isChecked():
            return self._manual_text.toPlainText().strip()
        if self._selected_result and self._address_verified:
            return self._label_for(self._selected_result)
        return self._search_box.text().strip()

    def coords(self) -> tuple[float, float] | None:
        """Return selected latitude/longitude when the address is provider-verified."""
        if not self._selected_result or not self._address_verified:
            return None
        lat, lng = self._extract_lat_lng(self._selected_result)
        if lat is None or lng is None:
            return None
        return lat, lng

    def place_id(self) -> str:
        if not self._selected_result or not self._address_verified:
            return ""
        return str(
            self._selected_result.get("place_id")
            or self._selected_result.get("id")
            or self._selected_result.get("mapbox_id")
            or ""
        )

    def address_verified(self) -> bool:
        return self._address_verified

    def selected_data(self) -> dict[str, Any]:
        return dict(self._selected_result or {})

    def set_manual_value(self, value: str) -> None:
        self._selected_result = None
        self._address_verified = False
        self._manual_toggle.setChecked(True)
        self._manual_text.setPlainText((value or "").strip())
        self._search_box.setText((value or "").strip())
        self._suggestions.setVisible(False)

    def _on_manual_toggled(self, checked: bool) -> None:
        self._manual_text.setVisible(checked)
        if checked:
            self._selected_result = None
            self._address_verified = False
            self._suggestions.setVisible(False)

    def _on_text_changed(self, _text: str) -> None:
        if self._selecting_suggestion:
            return
        self._selected_result = None
        self._address_verified = False
        self._debounce.start()

    def _start_lookup(self) -> None:
        if self._manual_toggle.isChecked():
            return
        query = self._search_box.text().strip()
        if not query:
            self._suggestions.clear()
            self._suggestions.setVisible(False)
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
            self._suggestions.setVisible(False)

    def _populate(self, results: list[dict[str, Any]]) -> None:
        self._suggestions.clear()
        for result in results:
            label = self._label_for(result)
            if not label:
                continue
            item = QListWidgetItem(label)
            item.setData(32, result)
            self._suggestions.addItem(item)
        self._suggestions.setVisible(self._suggestions.count() > 0)

    def _select_suggestion(self, item: QListWidgetItem) -> None:
        result = dict(item.data(32) or {"label": item.text()})
        label = self._label_for(result) or item.text()
        self._selected_result = result
        self._address_verified = True
        self._selecting_suggestion = True
        try:
            self._search_box.setText(label)
        finally:
            self._selecting_suggestion = False
        self._suggestions.setVisible(False)
        self.selected.emit(result)

    @staticmethod
    def _label_for(result: dict[str, Any]) -> str:
        return str(
            result.get("label")
            or result.get("place_name")
            or result.get("display_name")
            or result.get("formatted_address")
            or result.get("address")
            or ""
        ).strip()

    @staticmethod
    def _extract_lat_lng(result: dict[str, Any]) -> tuple[float | None, float | None]:
        lat = result.get("lat", result.get("latitude"))
        lng = result.get("lng", result.get("lon", result.get("longitude")))
        center = result.get("center") or result.get("coordinates")
        if (lat is None or lng is None) and isinstance(center, (list, tuple)) and len(center) >= 2:
            lng, lat = center[0], center[1]
        try:
            return (float(lat), float(lng))
        except (TypeError, ValueError):
            return (None, None)
