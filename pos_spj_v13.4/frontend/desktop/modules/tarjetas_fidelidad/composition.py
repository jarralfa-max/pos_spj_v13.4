"""Composition root for the Tarjetas Fidelidad desktop module (LOY-25).

Mirrors ``frontend/desktop/modules/fidelidad/composition.py``'s shape —
the ONLY place that wires a real, live ``connection``/``session_context``
into query services, command handlers and the presenter.
"""

from __future__ import annotations

from backend.application.loyalty_cards.authorization import LoyaltyCardsAuthorizationPolicy
from backend.application.loyalty_cards.session_authorization import (
    LoyaltyCardsSessionPermissionChecker,
)
from backend.application.loyalty_cards.use_cases.card_use_cases import (
    ActivateLoyaltyCardUseCase,
    BlockLoyaltyCardUseCase,
    IssueLoyaltyCardUseCase,
    UnblockLoyaltyCardUseCase,
)
from backend.application.loyalty_cards.use_cases.template_use_cases import (
    ActivateLoyaltyCardTemplateVersionUseCase,
    ApproveLoyaltyCardTemplateUseCase,
    ApproveLoyaltyCardTemplateVersionUseCase,
    CreateLoyaltyCardTemplateUseCase,
    CreateLoyaltyCardTemplateVersionUseCase,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import (
    LoyaltyCardsUnitOfWork,
)
from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_presenter import (
    TarjetasFidelidadPresenter,
)


def _get_card_by_number(connection, card_number: str):
    with LoyaltyCardsUnitOfWork(connection, owns_transaction=False) as uow:
        return uow.cards.get_by_number(card_number)


def build_tarjetas_fidelidad_presenter(connection, session_context=None) -> TarjetasFidelidadPresenter:
    checker = LoyaltyCardsSessionPermissionChecker(session_context)
    auth = LoyaltyCardsAuthorizationPolicy(checker)

    query_services = {
        "card_by_number": lambda card_number: _get_card_by_number(connection, card_number),
    }

    def _run(use_case_cls, **kwargs):
        return use_case_cls(auth).execute(connection, **kwargs)

    command_handlers = {
        "issue_card": lambda **kw: _run(IssueLoyaltyCardUseCase, **kw),
        "activate_card": lambda **kw: _run(ActivateLoyaltyCardUseCase, **kw),
        "block_card": lambda **kw: _run(BlockLoyaltyCardUseCase, **kw),
        "unblock_card": lambda **kw: _run(UnblockLoyaltyCardUseCase, **kw),
        "create_template": lambda **kw: _run(CreateLoyaltyCardTemplateUseCase, **kw),
        "approve_template": lambda **kw: _run(ApproveLoyaltyCardTemplateUseCase, **kw),
        "create_template_version": lambda **kw: _run(
            CreateLoyaltyCardTemplateVersionUseCase, **kw),
        "approve_template_version": lambda **kw: _run(
            ApproveLoyaltyCardTemplateVersionUseCase, **kw),
        "activate_template_version": lambda **kw: _run(
            ActivateLoyaltyCardTemplateVersionUseCase, **kw),
    }

    return TarjetasFidelidadPresenter(
        session_context=session_context, query_services=query_services,
        command_handlers=command_handlers)


def create_tarjetas_fidelidad_view(connection, session_context=None, parent=None):
    """Factory used by ``modulos/tarjetas_fidelidad_enterprise.py``. Never
    receives the container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_workspace import (
        TarjetasFidelidadWorkspace,
    )

    presenter = build_tarjetas_fidelidad_presenter(connection, session_context)
    return TarjetasFidelidadWorkspace(presenter, parent)
