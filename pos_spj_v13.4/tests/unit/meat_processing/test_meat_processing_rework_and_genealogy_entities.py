from decimal import Decimal

import pytest

from backend.domain.meat_processing.entities.process_genealogy_link import ProcessGenealogyLink
from backend.domain.meat_processing.entities.rework_order import ReworkOrder
from backend.domain.meat_processing.enums import ReworkOrigin, ReworkOrderStatus
from backend.domain.meat_processing.exceptions import (
    MeatProcessingInvariantError,
    MeatProcessingSegregationOfDutiesError,
    MeatProcessingStateTransitionError,
)
from backend.shared.ids import new_uuid


# -- ReworkOrder -----------------------------------------------------------------

def _rework(**overrides) -> ReworkOrder:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), source_output_id=new_uuid(),
        product_id=new_uuid(), origin=ReworkOrigin.QUALITY_DECISION,
        created_by_user_id=new_uuid(), quantity=Decimal("5"), weight=Decimal("5"))
    base.update(overrides)
    return ReworkOrder(**base)


def test_rework_requires_positive_quantity_or_weight():
    with pytest.raises(MeatProcessingInvariantError):
        _rework(quantity=Decimal("0"), weight=Decimal("0"))


def test_rework_requires_canonical_origin():
    with pytest.raises(MeatProcessingInvariantError):
        _rework(origin="QUALITY_DECISION")


def test_rework_full_lifecycle():
    rework = _rework()
    assert rework.status is ReworkOrderStatus.CREATED
    rework.approve(actor_user_id=new_uuid())
    assert rework.status is ReworkOrderStatus.APPROVED
    new_order_id = new_uuid()
    rework.start_execution(processing_order_id=new_order_id)
    assert rework.status is ReworkOrderStatus.IN_PROGRESS
    assert rework.processing_order_id == new_order_id
    rework.complete()
    assert rework.status is ReworkOrderStatus.COMPLETED
    rework.close()
    assert rework.status is ReworkOrderStatus.CLOSED


def test_rework_creator_cannot_approve_own_order():
    creator = new_uuid()
    rework = _rework(created_by_user_id=creator)
    with pytest.raises(MeatProcessingSegregationOfDutiesError):
        rework.approve(actor_user_id=creator)


def test_rework_cannot_execute_before_approval():
    rework = _rework()
    with pytest.raises(MeatProcessingStateTransitionError):
        rework.start_execution(processing_order_id=new_uuid())


def test_rework_cancel_only_from_created_or_approved():
    rework = _rework()
    rework.approve(actor_user_id=new_uuid())
    rework.start_execution(processing_order_id=new_uuid())
    with pytest.raises(MeatProcessingStateTransitionError):
        rework.cancel()


def test_rework_cancel_from_created():
    rework = _rework()
    rework.cancel()
    assert rework.status is ReworkOrderStatus.CANCELLED


# -- ProcessGenealogyLink -------------------------------------------------------

def _link(**overrides) -> ProcessGenealogyLink:
    base = dict(
        id=new_uuid(), operation_id=new_uuid(), upstream_entity_type="ProcessOutput",
        upstream_entity_id=new_uuid(), downstream_entity_type="MaterialConsumption",
        downstream_entity_id=new_uuid(), product_id=new_uuid(), linked_by_user_id=new_uuid())
    base.update(overrides)
    return ProcessGenealogyLink(**base)


def test_link_requires_entity_types():
    with pytest.raises(MeatProcessingInvariantError):
        _link(upstream_entity_type="  ")
    with pytest.raises(MeatProcessingInvariantError):
        _link(downstream_entity_type="")


def test_link_cannot_point_to_itself():
    same_id = new_uuid()
    with pytest.raises(MeatProcessingInvariantError):
        _link(upstream_entity_type="ProcessOutput", upstream_entity_id=same_id,
              downstream_entity_type="ProcessOutput", downstream_entity_id=same_id)


def test_link_rejects_negative_quantity():
    with pytest.raises(MeatProcessingInvariantError):
        _link(quantity=Decimal("-1"))


def test_link_allows_different_types_with_same_id():
    # A different entity_type with the same id is not a self-link.
    shared_id = new_uuid()
    link = _link(upstream_entity_type="ProcessOutput", upstream_entity_id=shared_id,
                 downstream_entity_type="MaterialConsumption", downstream_entity_id=shared_id)
    assert link.upstream_entity_id == link.downstream_entity_id
