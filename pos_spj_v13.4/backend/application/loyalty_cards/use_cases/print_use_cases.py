"""Loyalty Card batch printing use cases (LOY-22, master prompt §50-51:
"PrintJob integration, reprints").

A first draft tried to reuse `backend.domain.document_output.entities.
print_job.PrintJob` directly — it turned out `print_jobs.
template_version_id` carries a real, enforced foreign key to
`document_template_versions(id)` at the schema level, which a
`LoyaltyCardTemplateVersion` id cannot satisfy without also materializing a
matching row in a completely different template model (ESC_POS/HTML/PDF/
ZPL text templates, not our declarative visual card designs). See
`backend/domain/loyalty_cards/entities/loyalty_card_print_job.py`'s own
docstring for the full story — this module now uses that in-context
`LoyaltyCardPrintJob` instead, mirroring `PrintJob`'s lifecycle SHAPE for
conceptual consistency without the cross-schema FK risk.

Scope boundary: `LoyaltyCardPrintJob` tracks the RENDER step only (did a
valid PDF get produced) — whether a specific physical card was actually
handed to a printer is `LoyaltyCardBatchItem.status` (LOY-21)'s own
concern; the two are deliberately not merged.
"""

from __future__ import annotations

import json

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from backend.application.loyalty_cards.result import LoyaltyCardResult, fail_from_domain_error
from backend.application.loyalty_cards.use_cases._base import _LoyaltyCardsBaseUseCase
from backend.domain.loyalty_cards.entities.loyalty_card_print_job import LoyaltyCardPrintJob
from backend.domain.loyalty_cards.exceptions import (
    InvalidCardDesignSchemaError,
    LoyaltyCardBatchNotFoundError,
    LoyaltyCardDomainError,
    LoyaltyCardImpositionProfileNotFoundError,
    LoyaltyCardPrintJobNotFoundError,
    LoyaltyCardSheetProfileNotFoundError,
    LoyaltyCardTemplateNotFoundError,
    LoyaltyCardTemplateVersionNotFoundError,
)
from backend.infrastructure.db.repositories.loyalty_cards.unit_of_work import LoyaltyCardsUnitOfWork
from backend.infrastructure.loyalty_cards.print_renderer import PrintUnit, render_batch_pdf


def _build_print_units(uow: LoyaltyCardsUnitOfWork, batch_id: str,
                        card_placeholder_values: dict[str, dict[str, str]],
                        only_sheet_number: int | None) -> list[PrintUnit]:
    items = uow.batch_items.list_for_batch(batch_id)
    if only_sheet_number is not None:
        items = [item for item in items if item.sheet_number == only_sheet_number]
    return [
        PrintUnit(card_id=item.card_id, sheet_number=item.sheet_number,
                  position_in_sheet=item.position_in_sheet,
                  placeholder_values=card_placeholder_values.get(item.card_id, {}))
        for item in items
    ]


def _load_render_inputs(uow: LoyaltyCardsUnitOfWork, batch_id: str):
    """Returns `(design_schema, sheet, imposition)` or a `LoyaltyCardResult`
    failure if anything the batch references no longer exists."""
    batch = uow.batches.get(batch_id)
    if batch is None:
        return LoyaltyCardBatchNotFoundError(f"Lote {batch_id} no existe")
    template = uow.templates.get(batch.template_id)
    if template is None or template.active_version_id is None:
        return LoyaltyCardTemplateNotFoundError(
            f"Plantilla {batch.template_id} no existe o no tiene versión activa")
    version = uow.template_versions.get(template.active_version_id)
    if version is None:
        return LoyaltyCardTemplateVersionNotFoundError(
            f"Versión {template.active_version_id} no existe")
    imposition = uow.imposition_profiles.get(batch.imposition_profile_id)
    if imposition is None:
        return LoyaltyCardImpositionProfileNotFoundError(
            f"Perfil de imposición {batch.imposition_profile_id} no existe")
    sheet = uow.sheet_profiles.get(imposition.sheet_profile_id)
    if sheet is None:
        return LoyaltyCardSheetProfileNotFoundError(f"Pliego {imposition.sheet_profile_id} no existe")
    return json.loads(version.design_schema_json), sheet, imposition


def _render(design_schema: dict, sheet, imposition, print_units: list[PrintUnit]) -> bytes:
    return render_batch_pdf(
        sheet_width_mm=sheet.width_mm, sheet_height_mm=sheet.height_mm,
        margin_left_mm=sheet.margin_left_mm, margin_top_mm=sheet.margin_top_mm,
        columns=imposition.columns, rows=imposition.rows,
        card_width_mm=imposition.card_width_mm, card_height_mm=imposition.card_height_mm,
        bleed_mm=imposition.bleed_mm, gutter_horizontal_mm=imposition.gutter_horizontal_mm,
        gutter_vertical_mm=imposition.gutter_vertical_mm, design_schema=design_schema,
        print_units=print_units)


class RenderLoyaltyCardBatchUseCase(_LoyaltyCardsBaseUseCase):
    """Renders a batch (or a single sheet of it, via `only_sheet_number`)
    to a real PDF, wrapped in a `LoyaltyCardPrintJob` for queue/audit
    tracking."""

    def execute(
        self, connection, *, batch_id: str, card_placeholder_values: dict[str, dict[str, str]],
        actor_user_id: str, operation_id: str, only_sheet_number: int | None = None,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.BATCH_PRINT)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                batch = uow.batches.get(batch_id)
                if batch is None:
                    return fail_from_domain_error(
                        LoyaltyCardBatchNotFoundError(f"Lote {batch_id} no existe"),
                        operation_id=operation_id)

                inputs = _load_render_inputs(uow, batch_id)
                if isinstance(inputs, LoyaltyCardDomainError):
                    return fail_from_domain_error(inputs, operation_id=operation_id)
                design_schema, sheet, imposition = inputs

                job = LoyaltyCardPrintJob.create(
                    batch_id, requested_by_user_id=actor_user_id,
                    only_sheet_number=only_sheet_number)
                uow.print_jobs.save(job)
                job.start_rendering()
                uow.print_jobs.save(job)

                print_units = _build_print_units(
                    uow, batch_id, card_placeholder_values, only_sheet_number)
                try:
                    pdf_bytes = _render(design_schema, sheet, imposition, print_units)
                except InvalidCardDesignSchemaError as exc:
                    job.fail(str(exc))
                    uow.print_jobs.save(job)
                    return fail_from_domain_error(exc, operation_id=operation_id)

                job.mark_ready()
                uow.print_jobs.save(job)
            return LoyaltyCardResult.ok(
                "PDF de lote renderizado", entity_id=job.id, operation_id=operation_id,
                pdf_size_bytes=len(pdf_bytes),
                sheets_rendered=len({u.sheet_number for u in print_units}))
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)


class ReprintLoyaltyCardBatchUseCase(_LoyaltyCardsBaseUseCase):
    """§50-51: a reprint is always a NEW `LoyaltyCardPrintJob` linked back
    to the original via `reprint_of_job_id`, never a mutation of the
    original — and always carries a reason."""

    def execute(
        self, connection, *, original_job_id: str, reason: str,
        card_placeholder_values: dict[str, dict[str, str]], actor_user_id: str,
        operation_id: str,
    ) -> LoyaltyCardResult:
        try:
            self._auth.require(actor_user_id, LoyaltyCardsPermissions.REPRINT)
            with LoyaltyCardsUnitOfWork(connection) as uow:
                original = uow.print_jobs.get(original_job_id)
                if original is None:
                    return fail_from_domain_error(
                        LoyaltyCardPrintJobNotFoundError(
                            f"Trabajo de impresión {original_job_id} no existe"),
                        operation_id=operation_id)
                reprint_job = original.create_reprint(
                    requested_by_user_id=actor_user_id, reason=reason)
                uow.print_jobs.save(reprint_job)
                reprint_job.start_rendering()
                uow.print_jobs.save(reprint_job)

                inputs = _load_render_inputs(uow, original.batch_id)
                if isinstance(inputs, LoyaltyCardDomainError):
                    return fail_from_domain_error(inputs, operation_id=operation_id)
                design_schema, sheet, imposition = inputs

                print_units = _build_print_units(
                    uow, original.batch_id, card_placeholder_values, reprint_job.only_sheet_number)
                try:
                    pdf_bytes = _render(design_schema, sheet, imposition, print_units)
                except InvalidCardDesignSchemaError as exc:
                    reprint_job.fail(str(exc))
                    uow.print_jobs.save(reprint_job)
                    return fail_from_domain_error(exc, operation_id=operation_id)

                reprint_job.mark_ready()
                uow.print_jobs.save(reprint_job)
            return LoyaltyCardResult.ok(
                "Reimpresión renderizada", entity_id=reprint_job.id, operation_id=operation_id,
                pdf_size_bytes=len(pdf_bytes), reprint_of_job_id=original_job_id)
        except LoyaltyCardDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
