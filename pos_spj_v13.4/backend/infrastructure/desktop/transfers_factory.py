"""Desktop composition root for the canonical Transfers workspace."""
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter
from frontend.desktop.modules.transfers.transfers_view import TransfersView
from backend.infrastructure.db.repositories.transfers import TransferWorkspaceQueryRepository


class TransfersModuleHost(TransfersView):
    def __init__(self, container, parent=None) -> None:
        session = getattr(container, "session", None)
        permission = (session.tiene_permiso if session is not None
                      and hasattr(session, "tiene_permiso") else lambda _code: False)
        query = TransferWorkspaceQueryRepository(container.db)
        super().__init__(TransfersPresenter(query), has_permission=permission, parent=parent)
