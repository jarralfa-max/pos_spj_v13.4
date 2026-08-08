"""Shared page scaffolding for the finance module.

Thin wrapper over the canonical ``WorklistPage`` (FASE 6 UI/UX — previously
Finanzas reimplemented this scaffold on its own, without ViewState empty/error
handling; see MIGRATION_LOG.md). Pages only render widgets, capture input and
delegate to the presenter. No SQL, no business rules, no inline colors.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.components.worklist_page import WorklistPage


class FinancePage(WorklistPage):
    """Base page: PageHeader + optional KPI bar + StandardTable + refresh.

    Finance pages are simple lists — no search box, no server pagination
    (their presenter methods don't take query/offset params) — so both are
    off by default. A page can still set ``searchable``/``paginated`` = True
    once its presenter method supports it.
    """

    title: str = ""
    subtitle: str = ""
    columns: list[ColumnSpec] = []
    searchable = False
    paginated = False
