"""Presentation orchestration; business calculations stay in QueryServices."""
from backend.application.transfers.queries.workspace_query_service import (
    TransferPageViewModel, TransfersWorkspaceQueryService,
)


class TransfersPresenter:
    def __init__(self, query_service: TransfersWorkspaceQueryService) -> None:
        self._query_service = query_service

    def load_page(self, page_id: str, search: str = "") -> TransferPageViewModel:
        return self._query_service.page(page_id=page_id, search=search)
