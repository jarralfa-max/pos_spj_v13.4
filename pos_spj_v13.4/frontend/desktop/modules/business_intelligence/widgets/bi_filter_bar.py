"""Barra de filtros de sucursal y periodo de las páginas de BI (SDLC-BI-001).

Las sucursales llegan ya acotadas al usuario por `BiFilterState`; este widget no
filtra nada y no decide alcance.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from frontend.desktop.components.date_range_filter import DateRangeFilter
from frontend.desktop.components.dialogs import MessageDialog
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.modules.business_intelligence.presenters.bi_filters import (
    ALL_BRANCHES_LABEL,
    PERIOD_PRESETS,
)
from frontend.desktop.themes.tokens import TouchTarget


class BiFilterBar(QWidget):
    filters_changed = pyqtSignal()

    def __init__(self, state, parent=None) -> None:
        super().__init__(parent)
        self._state = state

        self.branch_selector = SearchableComboBox(self, placeholder=ALL_BRANCHES_LABEL)
        self.branch_selector.setMinimumHeight(TouchTarget.MIN_HEIGHT)
        self.branch_selector.setAccessibleName("Sucursal")
        self.branch_selector.set_options(state.branch_options())
        if not state.allows_all_branches:
            self.branch_selector.removeItem(0)     # "todas" no es una opción para él
        self.branch_selector.set_current_id(state.selected_branch_id)

        self.period_selector = QComboBox(self)
        self.period_selector.setMinimumHeight(TouchTarget.MIN_HEIGHT)
        self.period_selector.setAccessibleName("Periodo")
        for preset, label in PERIOD_PRESETS:
            self.period_selector.addItem(label, preset)
        self.period_selector.setCurrentIndex(self.period_selector.findData("month"))

        self.date_range = DateRangeFilter(self)
        self.date_range.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Sucursal", self))
        layout.addWidget(self.branch_selector)
        layout.addWidget(QLabel("Periodo", self))
        layout.addWidget(self.period_selector)
        layout.addWidget(self.date_range)
        layout.addStretch(1)

        self.branch_selector.currentIndexChanged.connect(self._apply)
        self.period_selector.currentIndexChanged.connect(self._apply)
        self.date_range.range_changed.connect(self._apply)

    def _apply(self, *_args) -> None:
        preset = self.period_selector.currentData()
        self.date_range.setVisible(preset == "custom")
        rango = self.date_range.value()
        desde, hasta = "", ""
        if preset == "custom":
            desde = rango.start.toString("yyyy-MM-dd")
            hasta = rango.end.toString("yyyy-MM-dd")
        try:
            self._state.set(branch_id=str(self.branch_selector.currentData() or ""),
                            preset=preset, date_from=desde, date_to=hasta)
        except Exception as exc:  # noqa: BLE001 - el rechazo se muestra, no tumba la página
            MessageDialog.warning(self, "Inteligencia de negocios", str(exc))
            return
        self.filters_changed.emit()
