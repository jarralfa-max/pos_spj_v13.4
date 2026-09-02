"""Use cases for the "Pantalla del cliente" section's advertising cards
(Contenido/Campañas/Slots/Asignaciones) — SET-18 cutover. Same shape as
`document_template_use_cases.py`/`marketing_campaign_use_cases.py`: thin
orchestration over `backend/domain/customer_display/` (SET-18),
construct/mutate the entity, persist.

`ChangeContentCampaignStatusUseCase` is deliberately ONE use case for all
7 approval-lifecycle transitions — same "one class, many actions" shape
as `ChangeTemplateVersionStatusUseCase`. Unlike that one, `ACTIVATE`
never needs to deactivate a "current active" sibling first: several
`ContentCampaign`s may be ACTIVE (and placed on different slots)
simultaneously — there is no one-active-per-something constraint here,
unlike `DocumentTemplateVersion`'s one-active-per-template rule.

`AssignCampaignPlacementUseCase` calls the existing, already-built
`campaign_placement_policy.assign_placement()` — never reinvented here.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.entities.campaign_placement import CampaignPlacement
from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import ContentType, CustomerDisplayMode
from backend.domain.customer_display.exceptions import (
    CampaignPlacementSlotOccupiedError,
    CustomerDisplayNotFoundError,
)
from backend.domain.customer_display.policies.campaign_placement_policy import assign_placement
from backend.infrastructure.db.repositories.customer_display.advertising_slot_repository import (
    SqliteAdvertisingSlotRepository,
)
from backend.infrastructure.db.repositories.customer_display.campaign_placement_repository import (
    SqliteCampaignPlacementRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_repository import (
    SqliteContentRepository,
)


class ContentStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class ContentCampaignStatusAction(str, Enum):
    SUBMIT_FOR_APPROVAL = "SUBMIT_FOR_APPROVAL"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"
    EXPIRE = "EXPIRE"
    ARCHIVE = "ARCHIVE"


class AdvertisingSlotStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


# ── Content ──────────────────────────────────────────────────────────────────

class CreateContentUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._content = SqliteContentRepository(connection)

    def execute(
        self, *, title: str, content_type: ContentType | str, body: str, duration_seconds: int = 10,
    ) -> Content:
        content = Content.create(
            title=title, content_type=ContentType(content_type), body=body,
            duration_seconds=duration_seconds,
        )
        self._content.save(content)
        self._conn.commit()
        return content


class UpdateContentUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._content = SqliteContentRepository(connection)

    def execute(self, *, content_id: str, title: str, body: str, duration_seconds: int = 10) -> Content:
        content = self._content.get(content_id)
        if content is None:
            raise CustomerDisplayNotFoundError(f"Contenido {content_id} no encontrado")
        content.update_details(title=title, body=body, duration_seconds=duration_seconds)
        self._content.save(content)
        self._conn.commit()
        return content


class ChangeContentStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._content = SqliteContentRepository(connection)

    def execute(self, *, content_id: str, action: ContentStatusAction) -> Content:
        content = self._content.get(content_id)
        if content is None:
            raise CustomerDisplayNotFoundError(f"Contenido {content_id} no encontrado")

        if action is ContentStatusAction.ACTIVATE:
            content.activate()
        elif action is ContentStatusAction.DEACTIVATE:
            content.deactivate()

        self._content.save(content)
        self._conn.commit()
        return content


# ── ContentCampaign ──────────────────────────────────────────────────────────

class CreateContentCampaignUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteContentCampaignRepository(connection)

    def execute(
        self, *, name: str, content_id: str, starts_at: str | None = None, ends_at: str | None = None,
        created_by_user_id: str | None = None,
    ) -> ContentCampaign:
        campaign = ContentCampaign.create(
            name=name, content_id=content_id, starts_at=starts_at, ends_at=ends_at,
            created_by_user_id=created_by_user_id,
        )
        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign


class UpdateContentCampaignUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteContentCampaignRepository(connection)

    def execute(
        self, *, campaign_id: str, starts_at: str | None = None, ends_at: str | None = None,
    ) -> ContentCampaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise CustomerDisplayNotFoundError(f"Campaña {campaign_id} no encontrada")
        campaign.update_schedule(starts_at=starts_at, ends_at=ends_at)
        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign


class ChangeContentCampaignStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteContentCampaignRepository(connection)

    def execute(
        self, *, campaign_id: str, action: ContentCampaignStatusAction, actor_user_id: str = "",
        reason: str = "",
    ) -> ContentCampaign:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise CustomerDisplayNotFoundError(f"Campaña {campaign_id} no encontrada")

        if action is ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL:
            campaign.submit_for_approval()
        elif action is ContentCampaignStatusAction.APPROVE:
            campaign.approve(actor_user_id)
        elif action is ContentCampaignStatusAction.REJECT:
            campaign.reject(reason)
        elif action is ContentCampaignStatusAction.ACTIVATE:
            campaign.activate(actor_user_id)
        elif action is ContentCampaignStatusAction.DEACTIVATE:
            campaign.deactivate()
        elif action is ContentCampaignStatusAction.EXPIRE:
            campaign.expire()
        elif action is ContentCampaignStatusAction.ARCHIVE:
            campaign.archive()

        self._campaigns.save(campaign)
        self._conn.commit()
        return campaign


# ── AdvertisingSlot ──────────────────────────────────────────────────────────

class CreateAdvertisingSlotUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._slots = SqliteAdvertisingSlotRepository(connection)

    def execute(self, *, code: str, mode: CustomerDisplayMode | str, display_order: int = 0) -> AdvertisingSlot:
        slot = AdvertisingSlot.create(code=code, mode=CustomerDisplayMode(mode), display_order=display_order)
        self._slots.save(slot)
        self._conn.commit()
        return slot


class UpdateAdvertisingSlotUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._slots = SqliteAdvertisingSlotRepository(connection)

    def execute(self, *, slot_id: str, display_order: int) -> AdvertisingSlot:
        slot = self._slots.get(slot_id)
        if slot is None:
            raise CustomerDisplayNotFoundError(f"Slot {slot_id} no encontrado")
        slot.update_display_order(display_order)
        self._slots.save(slot)
        self._conn.commit()
        return slot


class ChangeAdvertisingSlotStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._slots = SqliteAdvertisingSlotRepository(connection)

    def execute(self, *, slot_id: str, action: AdvertisingSlotStatusAction) -> AdvertisingSlot:
        slot = self._slots.get(slot_id)
        if slot is None:
            raise CustomerDisplayNotFoundError(f"Slot {slot_id} no encontrado")

        if action is AdvertisingSlotStatusAction.ACTIVATE:
            slot.activate()
        elif action is AdvertisingSlotStatusAction.DEACTIVATE:
            slot.deactivate()

        self._slots.save(slot)
        self._conn.commit()
        return slot


# ── CampaignPlacement ────────────────────────────────────────────────────────

class AssignCampaignPlacementUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._campaigns = SqliteContentCampaignRepository(connection)
        self._slots = SqliteAdvertisingSlotRepository(connection)
        self._placements = SqliteCampaignPlacementRepository(connection)

    def execute(
        self, *, campaign_id: str, slot_id: str, assigned_by_user_id: str | None = None,
    ) -> CampaignPlacement:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise CustomerDisplayNotFoundError(f"Campaña {campaign_id} no encontrada")
        slot = self._slots.get(slot_id)
        if slot is None:
            raise CustomerDisplayNotFoundError(f"Slot {slot_id} no encontrado")

        if self._placements.get_active_for_slot(slot_id) is not None:
            raise CampaignPlacementSlotOccupiedError(
                f"El slot {slot.code!r} ya tiene una asignación activa; libéralo primero"
            )

        placement = assign_placement(campaign, slot, assigned_by_user_id=assigned_by_user_id)
        self._placements.save(placement)
        self._conn.commit()
        return placement


class UnassignCampaignPlacementUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._placements = SqliteCampaignPlacementRepository(connection)

    def execute(self, *, placement_id: str) -> CampaignPlacement:
        placement = self._placements.get(placement_id)
        if placement is None:
            raise CustomerDisplayNotFoundError(f"Asignación {placement_id} no encontrada")
        placement.unassign()
        self._placements.save(placement)
        self._conn.commit()
        return placement
