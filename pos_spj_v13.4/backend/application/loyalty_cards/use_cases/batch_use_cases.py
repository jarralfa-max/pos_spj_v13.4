"""Loyalty Card batch use cases (LOY-21, master prompt §43-44).

`CreateLoyaltyCardBatchUseCase` issues a real `LoyaltyCard` (+ its
`LoyaltyCardPublicToken`) for every `(customer_id, membership_id)` pair
given — deliberately built directly here rather than delegating to
`IssueLoyaltyCardUseCase` (gated on `CARD_CREATE`), since batch generation
is gated on the distinct `BATCH_CREATE` permission instead. Same "compose
via direct domain/repository calls, not another gated use case" discipline
already applied throughout this pipeline (LOY-14, LOY-19).
"""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card import LoyaltyCard
from backend.domain.loyalty_cards.entities.loyalty_card_batch import LoyaltyCardBatch
from backend.domain.loyalty_cards.entities.loyalty_card_batch_item import LoyaltyCardBatchItem
from backend.domain.loyalty_cards.entities.loyalty_card_token import LoyaltyCardPublicToken
from backend.domain.loyalty_cards.enums import LoyaltyCardType
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardBatchError,
    LoyaltyCardBatchItemNotFoundError,
    LoyaltyCardBatchNotFoundError,
    LoyaltyCardDomainError,
    LoyaltyCardImpositionProfileNotFoundError,
    LoyaltyCardTemplateNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


class CreateLoyaltyCardBatchUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, template_id: str, imposition_profile_id: str,
        recipients: list[tuple[str, str]], actor_user_id: str, actor_branch_id: str,
        operation_id: str, card_type: LoyaltyCardType = LoyaltyCardType.PHYSICAL,
    ) -> LoyaltyCardResult:
        """`recipients` is a list of `(customer_id, membership_id)` pairs —
        one physical card is issued per pair, in list order (which fixes
        each item's `sheet_number`/`position_in_sheet`, §43-44)."""
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.BATCH_CREATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = uow.templates.get(template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(f"Plantilla {template_id} no existe"),
                        operation_id=operation_id)
                if not template.is_available_for_issuance():
                    return fail_from_domain_error(
                        InvalidLoyaltyCardBatchError(
                            "La plantilla debe estar ACTIVE con una versión vigente"),
                        operation_id=operation_id)
                imposition = uow.imposition_profiles.get(imposition_profile_id)
                if imposition is None:
                    return fail_from_domain_error(
                        LoyaltyCardImpositionProfileNotFoundError(
                            f"Perfil de imposición {imposition_profile_id} no existe"),
                        operation_id=operation_id)

                batch = LoyaltyCardBatch.create(
                    template_id, imposition_profile_id, len(recipients),
                    imposition.cards_per_sheet, created_by_user_id=actor_user_id)
                uow.batches.save(batch)

                sequence = uow.cards.count_all()
                for index, (customer_id, membership_id) in enumerate(recipients):
                    sequence += 1
                    card = LoyaltyCard.issue(
                        f"LC-{sequence:08d}", card_type, customer_id, membership_id)
                    uow.cards.save(card)
                    token = LoyaltyCardPublicToken.issue(card.id)
                    uow.tokens.save(token)
                    item = LoyaltyCardBatchItem.create_for_index(
                        batch.id, card.id, index=index, cards_per_sheet=imposition.cards_per_sheet)
                    uow.batch_items.save(item)

                self._emit(uow, LoyaltyCardEvents.BATCH_CREATED, entity_id=batch.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, item_count=batch.item_count,
                           sheets_required=batch.sheets_required)
            return LoyaltyCardResult.ok(
                "Lote creado", entity_id=batch.id, operation_id=operation_id,
                sheets_required=batch.sheets_required)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class _LoyaltyCardBatchTransitionUseCase(_LoyaltyCardsBaseUseCase):
    permission_code: str = LoyaltyCardsPermissions.BATCH_APPROVE
    success_message: str = ""
    event_name: str | None = None

    def _transition(self, batch: LoyaltyCardBatch, **kwargs) -> None:
        raise NotImplementedError

    def execute(self, connection, *, batch_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str, **kwargs) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, self.permission_code)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                batch = uow.batches.get(batch_id)
                if batch is None:
                    return fail_from_domain_error(
                        LoyaltyCardBatchNotFoundError(f"Lote {batch_id} no existe"),
                        operation_id=operation_id)
                self._transition(batch, actor_user_id=actor_user_id, **kwargs)
                uow.batches.save(batch)
                if self.event_name is not None:
                    self._emit(uow, self.event_name, entity_id=batch.id,
                               operation_id=operation_id, branch_id=actor_branch_id,
                               actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok(self.success_message, entity_id=batch.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class SubmitLoyaltyCardBatchForApprovalUseCase(_LoyaltyCardBatchTransitionUseCase):
    permission_code = LoyaltyCardsPermissions.BATCH_CREATE
    success_message = "Lote enviado a aprobación"

    def _transition(self, batch: LoyaltyCardBatch, **_kwargs) -> None:
        batch.submit_for_approval()


class ApproveLoyaltyCardBatchUseCase(_LoyaltyCardBatchTransitionUseCase):
    success_message = "Lote aprobado"
    event_name = LoyaltyCardEvents.BATCH_APPROVED

    def _transition(self, batch: LoyaltyCardBatch, *, actor_user_id: str) -> None:
        batch.approve(actor_user_id)


class StartLoyaltyCardBatchPrintingUseCase(_LoyaltyCardBatchTransitionUseCase):
    permission_code = LoyaltyCardsPermissions.BATCH_PRINT
    success_message = "Impresión de lote iniciada"
    event_name = LoyaltyCardEvents.BATCH_PRINTING_STARTED

    def _transition(self, batch: LoyaltyCardBatch, **_kwargs) -> None:
        batch.start_printing()


class CancelLoyaltyCardBatchUseCase(_LoyaltyCardBatchTransitionUseCase):
    permission_code = LoyaltyCardsPermissions.BATCH_CREATE
    success_message = "Lote cancelado"
    event_name = LoyaltyCardEvents.BATCH_CANCELLED

    def _transition(self, batch: LoyaltyCardBatch, **_kwargs) -> None:
        batch.cancel()


class MarkLoyaltyCardBatchItemPrintedUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, item_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.BATCH_PRINT)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                item = uow.batch_items.get(item_id)
                if item is None:
                    return fail_from_domain_error(
                        LoyaltyCardBatchItemNotFoundError(f"Ítem {item_id} no existe"),
                        operation_id=operation_id)
                item.mark_printed()
                uow.batch_items.save(item)
                self._emit(uow, LoyaltyCardEvents.BATCH_ITEM_PRINTED, entity_id=item.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, card_id=item.card_id)

                if uow.batch_items.count_pending_for_batch(item.batch_id) == 0:
                    batch = uow.batches.get(item.batch_id)
                    if batch is not None:
                        batch.complete()
                        uow.batches.save(batch)
                        self._emit(uow, LoyaltyCardEvents.BATCH_COMPLETED, entity_id=batch.id,
                                   operation_id=operation_id, branch_id=actor_branch_id,
                                   actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Ítem marcado como impreso", entity_id=item.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class MarkLoyaltyCardBatchItemFailedUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, item_id: str, reason: str, actor_user_id: str,
                actor_branch_id: str, operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.BATCH_PRINT)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                item = uow.batch_items.get(item_id)
                if item is None:
                    return fail_from_domain_error(
                        LoyaltyCardBatchItemNotFoundError(f"Ítem {item_id} no existe"),
                        operation_id=operation_id)
                item.mark_failed(reason)
                uow.batch_items.save(item)
                self._emit(uow, LoyaltyCardEvents.BATCH_ITEM_FAILED, entity_id=item.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, reason=reason)
            return LoyaltyCardResult.ok("Ítem marcado como fallido", entity_id=item.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
