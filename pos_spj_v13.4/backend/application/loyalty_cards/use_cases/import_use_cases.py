"""Loyalty Card design import use case (LOY-19, master prompt §41-42).

Builds a canvas-ONLY design schema from a safely-imported source file — the
resulting `LoyaltyCardTemplateVersion` has an empty `elements` list; a human
still populates the actual elements in the Studio (LOY-18) afterward. Uses
`TEMPLATE_IMPORT` (a distinct permission from `TEMPLATE_EDIT`, both already
defined in LOY-1) — deliberately does NOT delegate to
`CreateLoyaltyCardTemplateVersionUseCase` (which gates on `TEMPLATE_EDIT`)
since that would silently require the wrong permission; it builds the
version directly within its own transaction instead, same "compose via
direct domain/repository calls, not another gated use case" discipline
already applied throughout this pipeline.
"""

from __future__ import annotations

import json

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card_template_version import (
    LoyaltyCardTemplateVersion,
)
from backend.domain.loyalty_cards.events import LoyaltyCardEvents
from backend.domain.loyalty_cards.exceptions import (
    LoyaltyCardDomainError,
    LoyaltyCardTemplateNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork
from backend.infrastructure.loyalty_cards.design_import import import_canvas_dimensions


class ImportLoyaltyCardDesignUseCase(_LoyaltyCardsBaseUseCase):
    def execute(
        self, connection, *, template_id: str, file_bytes: bytes, source_format: str,
        actor_user_id: str, actor_branch_id: str, operation_id: str, dpi: int = 300,
        background_color: str = "#FFFFFF",
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.TEMPLATE_IMPORT)
            # Raises InvalidCardDesignSchemaError (caught below) for anything
            # oversized, malformed, mismatched-format, or containing
            # disallowed SVG content — never touches the UoW until the file
            # is proven safe.
            dimensions = import_canvas_dimensions(file_bytes, source_format, dpi=dpi)

            with LoyaltyCardsUnitOfWork(connection) as uow:
                template = uow.templates.get(template_id)
                if template is None:
                    return fail_from_domain_error(
                        LoyaltyCardTemplateNotFoundError(f"Plantilla {template_id} no existe"),
                        operation_id=operation_id)
                design_schema_json = json.dumps({
                    "canvas": {
                        "width_mm": dimensions["width_mm"],
                        "height_mm": dimensions["height_mm"],
                        "background_color": background_color,
                    },
                    "elements": [],
                })
                next_number = uow.template_versions.count_for_template(template_id) + 1
                version = LoyaltyCardTemplateVersion.create(
                    template_id, next_number, design_schema_json,
                    created_by_user_id=actor_user_id)
                uow.template_versions.save(version)
                self._emit(uow, LoyaltyCardEvents.TEMPLATE_VERSION_CREATED,
                           entity_id=version.id, operation_id=operation_id,
                           branch_id=actor_branch_id, actor_user_id=actor_user_id,
                           template_id=template_id, version_number=next_number,
                           imported_from=source_format)
            return LoyaltyCardResult.ok(
                "Diseño importado (solo canvas — agregar elementos en el Estudio)",
                entity_id=version.id, operation_id=operation_id, version_number=next_number,
                canvas=dimensions)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
