from decimal import Decimal

import pytest

from backend.domain.losses.entities.loss_classification import LossClassification
from backend.domain.losses.entities.loss_reason import LossReason
from backend.domain.losses.enums import (
    LossClassificationCode, LossOrigin, MaterialDispositionKind,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.policies.loss_approval_policy import LossApprovalPolicy
from backend.domain.losses.policies.loss_classification_policy import LossClassificationPolicy
from backend.domain.losses.policies.loss_registration_policy import LossRegistrationPolicy
from backend.shared.ids import new_uuid


def test_classifications_and_reasons_are_configurable_entities():
    classification = LossClassification(
        id=new_uuid(), code=LossClassificationCode.EXPIRY,
        display_name="Caducidad", active=True,
    )
    reason = LossReason(
        id=new_uuid(), classification_id=classification.id,
        code="COLD_ROOM_ROTATION", display_name="Rotación incorrecta", active=True,
    )
    assert reason.classification_id == classification.id


def test_coproduct_and_byproduct_are_not_automatically_losses():
    policy = LossClassificationPolicy()
    assert not policy.is_loss_material(MaterialDispositionKind.CO_PRODUCT)
    assert not policy.is_loss_material(MaterialDispositionKind.BY_PRODUCT)
    assert policy.is_loss_material(MaterialDispositionKind.WASTE)


def test_theoretical_loss_never_requests_inventory_posting():
    assert not LossRegistrationPolicy().requires_inventory_posting(
        LossClassificationCode.THEORETICAL_LOSS)
    assert LossRegistrationPolicy().requires_inventory_posting(
        LossClassificationCode.EXPIRY)


def test_origin_policy_requires_production_reference_for_process_loss():
    policy = LossRegistrationPolicy()
    with pytest.raises(LossInvariantError, match="producción"):
        policy.validate_origin(
            classification=LossClassificationCode.PROCESS_LOSS,
            origin=LossOrigin.PRODUCTION,
            source_document_id=None,
        )


def test_approval_policy_has_no_implicit_limit_and_uses_decimal():
    policy = LossApprovalPolicy(approval_limit=Decimal("500"))
    assert not policy.requires_approval(Decimal("500"))
    assert policy.requires_approval(Decimal("500.01"))
    with pytest.raises(TypeError, match="Decimal"):
        LossApprovalPolicy(approval_limit=500.0)
