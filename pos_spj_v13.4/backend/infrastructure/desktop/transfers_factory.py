"""Desktop composition root for the canonical Transfers workspace."""
from backend.application.transfers.composition import TransferUseCaseFactory
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter
from frontend.desktop.modules.transfers.transfers_view import TransfersView
from backend.infrastructure.db.repositories.transfers import TransferWorkspaceQueryRepository


class TransfersModuleHost(TransfersView):
    def __init__(self, container, parent=None) -> None:
        session = getattr(container, "session", None)
        permission = (session.tiene_permiso if session is not None
                      and hasattr(session, "tiene_permiso") else lambda _code: False)
        query = TransferWorkspaceQueryRepository(container.db)
        factory = (TransferUseCaseFactory.from_session(session, connection=container.db)
                   if session is not None
                   else TransferUseCaseFactory.for_tests(connection=container.db))
        presenter = TransfersPresenter(
            query, connection=container.db,
            create_transfer_request_uc=factory.create_transfer_request(),
            session_context=session)
        super().__init__(presenter, has_permission=permission, parent=parent)
