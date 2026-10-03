"""Ruta con varios registros relacionados, una pestaña cada uno (LOY-29).

Cupones (emitidos / definiciones), Vales, Puntos (cuentas / movimientos),
Sorteos (campañas / participaciones / boletos / premios)… Cada pestaña es una
`LoyaltyRecordPage` independiente y carga al mostrarse por primera vez.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget

from frontend.desktop.components.pages import TabbedPage
from frontend.desktop.modules.fidelidad.records.record_page import LoyaltyRecordPage
from frontend.desktop.modules.fidelidad.records.specs import TabbedSpec


class LoyaltyTabbedRecordPage(TabbedPage):
    def __init__(self, presenter, spec: TabbedSpec, parent=None, *,
                 extra_tabs: tuple[tuple[str, QWidget, int], ...] = ()) -> None:
        super().__init__(parent, title=spec.title, subtitle=spec.subtitle)
        self.spec = spec
        self.setObjectName(f"fidelidadTabbedPage_{spec.key}")
        self.setAccessibleName(spec.title)
        self.pages: list[QWidget] = []
        for label, page_spec in spec.tabs:
            self._add(LoyaltyRecordPage(presenter, page_spec, self), label)
        for label, widget, index in extra_tabs:
            self.pages.insert(index, widget)
            self.tabs.insertTab(index, widget, label)
        self.tabs.currentChanged.connect(lambda _i: self.ensure_loaded())

    def _add(self, page: QWidget, label: str) -> None:
        self.pages.append(page)
        self.tabs.addTab(page, label)

    def page(self, key: str) -> LoyaltyRecordPage | None:
        for page in self.pages:
            if getattr(getattr(page, "spec", None), "key", None) == key:
                return page
        return None

    def ensure_loaded(self) -> None:
        current = self.tabs.currentWidget()
        if current is not None and hasattr(current, "ensure_loaded"):
            current.ensure_loaded()


__all__ = ["LoyaltyTabbedRecordPage"]
