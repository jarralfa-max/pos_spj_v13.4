"""LOY-17 — LoyaltyCardTemplate / LoyaltyCardTemplateVersion domain
entities (master prompt §33-34)."""

from __future__ import annotations

import json

import pytest

from backend.domain.loyalty_cards.entities.loyalty_card_template import LoyaltyCardTemplate
from backend.domain.loyalty_cards.entities.loyalty_card_template_version import (
    LoyaltyCardTemplateVersion,
)
from backend.domain.loyalty_cards.exceptions import (
    InvalidCardDesignSchemaError,
    InvalidLoyaltyCardTemplateError,
    InvalidLoyaltyCardTemplateStateError,
    InvalidLoyaltyCardTemplateVersionStateError,
)
from backend.shared.ids import new_uuid

_VALID_SCHEMA = json.dumps({
    "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
    "elements": [
        {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "40", "height_mm": "10",
         "content": "{{customer_name}}"},
    ],
})


class TestLoyaltyCardTemplate:
    def test_requires_code_and_name(self):
        with pytest.raises(InvalidLoyaltyCardTemplateError):
            LoyaltyCardTemplate.create("", "Plantilla", created_by_user_id=new_uuid())

    def test_lifecycle_happy_path(self):
        creator = new_uuid()
        template = LoyaltyCardTemplate.create("T1", "Plantilla clásica", created_by_user_id=creator)
        template.submit_for_approval()
        template.approve(new_uuid())
        version_id = new_uuid()
        template.activate(version_id)
        assert template.status.value == "ACTIVE"
        assert template.active_version_id == version_id
        assert template.is_available_for_issuance()

    def test_approver_cannot_be_creator(self):
        creator = new_uuid()
        template = LoyaltyCardTemplate.create("T1", "Plantilla", created_by_user_id=creator)
        template.submit_for_approval()
        with pytest.raises(InvalidLoyaltyCardTemplateStateError):
            template.approve(creator)

    def test_cannot_activate_from_draft(self):
        template = LoyaltyCardTemplate.create("T1", "Plantilla", created_by_user_id=new_uuid())
        with pytest.raises(InvalidLoyaltyCardTemplateStateError):
            template.activate(new_uuid())

    def test_reactivate_with_new_version_while_active(self):
        template = LoyaltyCardTemplate.create("T1", "Plantilla", created_by_user_id=new_uuid())
        template.submit_for_approval()
        template.approve(new_uuid())
        template.activate(new_uuid())
        new_version_id = new_uuid()
        template.activate(new_version_id)
        assert template.active_version_id == new_version_id

    def test_archive(self):
        template = LoyaltyCardTemplate.create("T1", "Plantilla", created_by_user_id=new_uuid())
        template.archive()
        assert template.status.value == "ARCHIVED"
        with pytest.raises(InvalidLoyaltyCardTemplateStateError):
            template.archive()


class TestLoyaltyCardTemplateVersion:
    def test_requires_design_schema(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            LoyaltyCardTemplateVersion.create(new_uuid(), 1, "", created_by_user_id=new_uuid())

    def test_lifecycle_happy_path(self):
        creator = new_uuid()
        version = LoyaltyCardTemplateVersion.create(
            new_uuid(), 1, _VALID_SCHEMA, created_by_user_id=creator)
        version.approve(new_uuid())
        version.activate()
        assert version.status.value == "ACTIVE"
        assert version.activated_at is not None

    def test_approver_cannot_be_creator(self):
        creator = new_uuid()
        version = LoyaltyCardTemplateVersion.create(
            new_uuid(), 1, _VALID_SCHEMA, created_by_user_id=creator)
        with pytest.raises(InvalidLoyaltyCardTemplateVersionStateError):
            version.approve(creator)

    def test_cannot_activate_without_approval(self):
        version = LoyaltyCardTemplateVersion.create(
            new_uuid(), 1, _VALID_SCHEMA, created_by_user_id=new_uuid())
        with pytest.raises(InvalidLoyaltyCardTemplateVersionStateError):
            version.activate()

    def test_archive(self):
        version = LoyaltyCardTemplateVersion.create(
            new_uuid(), 1, _VALID_SCHEMA, created_by_user_id=new_uuid())
        version.approve(new_uuid())
        version.activate()
        version.archive()
        assert version.status.value == "ARCHIVED"
