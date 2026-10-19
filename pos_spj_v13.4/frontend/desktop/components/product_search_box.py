"""Product search box wrapper."""

from __future__ import annotations

from frontend.desktop.components.search_selector import SearchProvider, SearchSelector


class ProductSearchBox(SearchSelector):
    def __init__(self, parent=None, *, provider: SearchProvider | None = None,
                 empty_reason_provider=None, collapse_when_empty: bool = False,
                 keep_selection: bool = False) -> None:
        super().__init__(parent, provider=provider, placeholder="Buscar producto...",
                         empty_reason_provider=empty_reason_provider,
                         collapse_when_empty=collapse_when_empty,
                         keep_selection=keep_selection)
