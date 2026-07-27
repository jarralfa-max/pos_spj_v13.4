"""Employee search box wrapper."""

from __future__ import annotations

from frontend.desktop.components.search_selector import SearchProvider, SearchSelector


class EmployeeSearchBox(SearchSelector):
    def __init__(self, parent=None, *, provider: SearchProvider | None = None) -> None:
        super().__init__(parent, provider=provider, placeholder="Buscar empleado...")
