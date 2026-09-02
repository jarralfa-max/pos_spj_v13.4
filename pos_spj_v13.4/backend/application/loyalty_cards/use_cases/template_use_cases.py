"""Loyalty Card template + template-version use cases (LOY-17, master
prompt §33-34).

A template may only be activated once it has at least one APPROVED
version — that cross-row check lives here (a repository lookup), not in
`LoyaltyCardTemplate.activate()` itself, which only knows its own fields.
Activating a NEW version of an already-ACTIVE template archives whichever
version was previously ACTIVE in the SAME transaction — a template never
has two ACTIVE versions at once.
"""

from __future__ import annotations

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card_template import LoyaltyCardTemplate
from backend.domain.loyalty_cards.entities.loyalty_card_template_version import (
    LoyaltyCardTemplateVersion,
)
from backend.domain.loyalty_cards.enums import LoyaltyCardTemplateStatus
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardTemplateStateError,
    LoyaltyCardDomainError,
    LoyaltyCardTemplateNotFoundError,
    LoyaltyCardTemplateVersionNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork


class CreateLoyaltyCardTemplateUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, code: str, name: str, actor_user_id: str, actor_branch_id: str,
        operation_id: str, **template_kwargs,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_CREATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = LoyaltyCardTemplate.create(
                    code, name, created_by_user_id=actor_user_id, **template_kwargs)
                template.submit_for_approval()
                uow.templates.save(template)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_CREATED, entity_id=template.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Plantilla creada", entity_id=template.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ApproveLoyaltyCardTemplateUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, template_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_APPROVE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = uow.templates.get(template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(f"Plantilla {template_id} no existe"),
                        operation_id=operation_id)
                template.approve(actor_user_id)
                uow.templates.save(template)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_APPROVED, entity_id=template.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Plantilla aprobada", entity_id=template.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ArchiveLoyaltyCardTemplateUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, template_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_ARCHIVE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = uow.templates.get(template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(f"Plantilla {template_id} no existe"),
                        operation_id=operation_id)
                template.archive()
                uow.templates.save(template)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_ARCHIVED, entity_id=template.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Plantilla archivada", entity_id=template.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class CreateLoyaltyCardTemplateVersionUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, template_id: str, design_schema_json: str, actor_user_id: str,
        actor_branch_id: str, operation_id: str,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_EDIT)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = uow.templates.get(template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(f"Plantilla {template_id} no existe"),
                        operation_id=operation_id)
                next_number = uow.template_versions.count_for_template(template_id) + 1
                version = LoyaltyCardTemplateVersion.create(
                    template_id, next_number, design_schema_json,
                    created_by_user_id=actor_user_id)
                uow.template_versions.save(version)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_VERSION_CREATED,
                           entity_id=version.id, operation_id=operation_id,
                           branch_id=actor_branch_id, actor_user_id=actor_user_id,
                           template_id=template_id, version_number=next_number)
            return LoyaltyCardResult.ok(
                "Versión de plantilla creada", entity_id=version.id, operation_id=operation_id,
                version_number=next_number)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ApproveLoyaltyCardTemplateVersionUseCase(_LoyaltyCardsBaseUseCase):
    def execute(self, connection, *, version_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_APPROVE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                version = uow.template_versions.get(version_id)
                if version is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateVersionNotFoundError(f"Versión {version_id} no existe"),
                        operation_id=operation_id)
                version.approve(actor_user_id)
                uow.template_versions.save(version)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_VERSION_APPROVED,
                           entity_id=version.id, operation_id=operation_id,
                           branch_id=actor_branch_id, actor_user_id=actor_user_id)
            return LoyaltyCardResult.ok("Versión aprobada", entity_id=version.id,
                                        operation_id=operation_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ActivateLoyaltyCardTemplateVersionUseCase(_LoyaltyCardsBaseUseCase):
    """Activates an APPROVED version as the template's live design.
    Archives the previously ACTIVE version of the SAME template (if any) in
    this same transaction, and activates the parent template itself if it
    was only APPROVED (never two ACTIVE versions at once, §33)."""

    def execute(self, connection, *, version_id: str, actor_user_id: str, actor_branch_id: str,
                operation_id: str) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_ACTIVATE)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                version = uow.template_versions.get(version_id)
                if version is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateVersionNotFoundError(f"Versión {version_id} no existe"),
                        operation_id=operation_id)
                template = uow.templates.get(version.template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(
                            f"Plantilla {version.template_id} no existe"),
                        operation_id=operation_id)
                if template.status not in (
                    LoyaltyCardTemplateStatus.APPROVED, LoyaltyCardTemplateStatus.ACTIVE,
                ):
                    return fail_from_domain_error(
                        InvalidLoyaltyCardTemplateStateError(
                            "La plantilla debe estar APPROVED o ACTIVE para activar una versión"),
                        operation_id=operation_id)

                previous_active = uow.template_versions.get_active_for_template(
                    version.template_id)
                if previous_active is not None and previous_active.id != version.id:
                    previous_active.archive()
                    uow.template_versions.save(previous_active)

                version.activate()
                uow.template_versions.save(version)
                template.activate(version.id)
                uow.templates.save(template)

                self._emit(uow, LoyaltyCardEvents.TEMPLATE_VERSION_ACTIVATED,
                           entity_id=version.id, operation_id=operation_id,
                           branch_id=actor_branch_id, actor_user_id=actor_user_id,
                           template_id=template.id)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_ACTIVATED, entity_id=template.id,
                           operation_id=operation_id, branch_id=actor_branch_id,
                           actor_user_id=actor_user_id, active_version_id=version.id)
            return LoyaltyCardResult.ok(
                "Versión activada", entity_id=version.id, operation_id=operation_id,
                template_id=template.id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
