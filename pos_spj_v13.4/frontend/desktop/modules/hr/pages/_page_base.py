"""Shared page scaffolding for the HR module.

Thin wrapper over the canonical ``WorklistPage`` (FASE 6 UI/UX — previously
RRHH reimplemented this scaffold on its own, without ViewState empty/error
handling; see MIGRATION_LOG.md). Pages only render widgets, capture input and
delegate to the presenter. No SQL, no business rules, no inline colors.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage


class HRPage(WorklistPage):
    """Base page: PageHeader + optional KPI bar + StandardTable + refresh.

    Most HR pages are short worklists (no search, no server pagination). A
    page sets ``searchable``/``paginated`` = True when its presenter method
    supports it — Empleados does (auditoría HR-28).
    """

    title: str = ""
    subtitle: str = ""
    columns: list[ColumnSpec] = []
    searchable = False
    paginated = False

    def _capabilities(self):
        getter = getattr(self._presenter, "capabilities", None)
        return getter() if getter is not None else None

    def _allowed(self, name: str) -> bool:
        capabilities = self._capabilities()
        return True if capabilities is None else bool(getattr(capabilities, name, False))

    def _add_action(self, button, capability: str | None, handler) -> None:
        """Botón de encabezado visible sólo si la sesión tiene la capacidad
        (HR-01: el backend lo vuelve a validar)."""
        button.clicked.connect(handler)
        button.setVisible(capability is None or self._allowed(capability))
        self.header.add_action(button)
