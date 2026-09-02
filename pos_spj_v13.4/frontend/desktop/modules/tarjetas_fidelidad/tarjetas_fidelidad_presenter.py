"""Presenter bridge between the Tarjetas Fidelidad desktop UI and backend
services (LOY-25). Mirrors
``frontend/desktop/modules/fidelidad/fidelidad_presenter.py``'s thin-bridge
shape exactly."""

from __future__ import annotations

from collections.abc import Callable

from backend.application.loyalty_cards.result import LoyaltyCardResult
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.shared.ids import new_uuid
from frontend.desktop.modules.tarjetas_fidelidad.capability_resolver import (
    resolve_tarjetas_fidelidad_capabilities,
)
from frontend.desktop.modules.tarjetas_fidelidad.view_models import (
    TarjetasFidelidadCapabilities,
)

_NOT_WIRED = "El módulo de Tarjetas Fidelidad no está disponible: falta la conexión al backend."


class TarjetasFidelidadPresenter:
    def __init__(
        self, *, session_context,
        query_services: dict[str, object] | None = None,
        command_handlers: dict[str, Callable[..., object]] | None = None,
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._command_handlers = dict(command_handlers or {})

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> TarjetasFidelidadCapabilities:
        return resolve_tarjetas_fidelidad_capabilities(self.can)

    def current_user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def current_branch_id(self) -> str:
        return str(getattr(self._session, "active_branch_id", "") or "")

    def query_service(self, key: str):
        return self._query_services.get(key)

    def command_handler(self, key: str) -> Callable[..., object] | None:
        return self._command_handlers.get(key)

    # -- Tarjetas ---------------------------------------------------------
    def find_card_by_number(self, card_number: str):
        service = self.query_service("card_by_number")
        return service(card_number) if service is not None else None

    def issue_card(self, *, customer_id: str, membership_id: str,
                   card_type: LoyaltyCardType = LoyaltyCardType.PHYSICAL) -> LoyaltyCardResult:
        handler = self.command_handler("issue_card")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            customer_id=customer_id, membership_id=membership_id, card_type=card_type,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    def activate_card(self, card_id: str) -> LoyaltyCardResult:
        handler = self.command_handler("activate_card")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            card_id=card_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def block_card(self, *, card_id: str, reason: str) -> LoyaltyCardResult:
        handler = self.command_handler("block_card")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            card_id=card_id, reason=reason, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def unblock_card(self, card_id: str) -> LoyaltyCardResult:
        handler = self.command_handler("unblock_card")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            card_id=card_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    # -- Plantillas ---------------------------------------------------------
    def create_template(self, *, code: str, name: str) -> LoyaltyCardResult:
        handler = self.command_handler("create_template")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            code=code, name=name, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def approve_template(self, template_id: str) -> LoyaltyCardResult:
        handler = self.command_handler("approve_template")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            template_id=template_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def create_template_version(self, *, template_id: str,
                                design_schema_json: str) -> LoyaltyCardResult:
        handler = self.command_handler("create_template_version")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            template_id=template_id, design_schema_json=design_schema_json,
            actor_user_id=self.current_user_id(), actor_branch_id=self.current_branch_id(),
            operation_id=new_uuid())

    def approve_template_version(self, version_id: str) -> LoyaltyCardResult:
        handler = self.command_handler("approve_template_version")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            version_id=version_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())

    def activate_template_version(self, version_id: str) -> LoyaltyCardResult:
        handler = self.command_handler("activate_template_version")
        if handler is None:
            return LoyaltyCardResult.fail(_NOT_WIRED, "NOT_WIRED")
        return handler(
            version_id=version_id, actor_user_id=self.current_user_id(),
            actor_branch_id=self.current_branch_id(), operation_id=new_uuid())
