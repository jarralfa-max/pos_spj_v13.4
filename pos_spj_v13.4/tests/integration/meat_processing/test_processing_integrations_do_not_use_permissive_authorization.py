"""§15/§25 — las integraciones de Procesamiento con otros contextos se
autorizan con una CONCESIÓN declarada por el contexto dueño: un conjunto
cerrado de permisos, para el mismo usuario que opera. Nada de "permitir todo".
"""
from __future__ import annotations

import pytest

from backend.application.costing.processing_costing import (
    COST_PROCESSING,
    CostingPermissionDeniedError,
    costing_policy_for,
)
from backend.application.inventory.integration_grants import inventory_policy_for
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.losses.yield_variance_case import losses_policy_for
from backend.application.meat_processing.integration_grants import meat_processing_policy_for
from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.quality.output_inspection import (
    QualityPermissionDeniedError,
    quality_policy_for,
)
from backend.application.quality.permissions import QualityPermissions
from backend.infrastructure.integrations.meat_processing_ports import (
    CanonicalProductionConsumptionAdapter,
    CanonicalProductionReceiptAdapter,
    InventoryMaterialReservationAdapter,
)
from backend.shared.ids import new_uuid

ACTOR = new_uuid()


def test_inventory_grants_processing_only_what_production_needs():
    _, checker = inventory_policy_for("meat_processing", ACTOR)
    for permitido in (InventoryPermissions.RESERVATION_CREATE,
                      InventoryPermissions.RESERVATION_RELEASE,
                      InventoryPermissions.MOVEMENT_CREATE, InventoryPermissions.LOT_CREATE):
        assert checker.has_permission(ACTOR, permitido)
    for ajeno in (InventoryPermissions.ADJUSTMENT_CREATE, InventoryPermissions.ADJUSTMENT_POST,
                  InventoryPermissions.MOVEMENT_REVERSE, InventoryPermissions.QUALITY_RELEASE,
                  InventoryPermissions.LOT_RELEASE):
        assert not checker.has_permission(ACTOR, ajeno), ajeno


def test_a_grant_is_for_the_operating_user_only():
    _, checker = inventory_policy_for("meat_processing", ACTOR)
    assert not checker.has_permission(new_uuid(), InventoryPermissions.RESERVATION_CREATE)


def test_every_decision_is_recorded():
    _, checker = inventory_policy_for("meat_processing", ACTOR)
    checker.has_permission(ACTOR, InventoryPermissions.RESERVATION_CREATE)
    checker.has_permission(ACTOR, InventoryPermissions.ADJUSTMENT_CREATE)
    assert [(d.permission_code, d.granted) for d in checker.decisions] == [
        (InventoryPermissions.RESERVATION_CREATE, True),
        (InventoryPermissions.ADJUSTMENT_CREATE, False)]


def test_quality_lets_processing_request_inspections_but_never_decide():
    politica = quality_policy_for("meat_processing", ACTOR)
    politica.require(ACTOR, QualityPermissions.INSPECTION_REQUEST)
    with pytest.raises(QualityPermissionDeniedError):
        politica.require(ACTOR, QualityPermissions.INSPECTION_DECIDE)


def test_costing_and_losses_grant_only_their_request():
    costing_policy_for("meat_processing", ACTOR).require(ACTOR, COST_PROCESSING)
    with pytest.raises(CostingPermissionDeniedError):
        costing_policy_for("meat_processing", new_uuid()).require(ACTOR, COST_PROCESSING)
    losses_policy_for("meat_processing", ACTOR)


def test_quality_callback_into_processing_is_limited_to_recording_the_decision():
    politica = meat_processing_policy_for("quality", ACTOR)
    politica.require(ACTOR, MeatProcessingPermissions.QUALITY_RECORD_DECISION)
    with pytest.raises(Exception):
        politica.require(ACTOR, MeatProcessingPermissions.ORDER_RELEASE)


@pytest.mark.parametrize("fabrica", [inventory_policy_for, quality_policy_for,
                                     costing_policy_for, losses_policy_for,
                                     meat_processing_policy_for])
def test_a_module_without_a_grant_gets_nothing(fabrica):
    from backend.domain.losses.exceptions import LossPermissionDeniedError
    from backend.domain.meat_processing.exceptions import MeatProcessingPermissionDeniedError

    with pytest.raises((PermissionError, LossPermissionDeniedError,
                        MeatProcessingPermissionDeniedError)):
        fabrica("modulo_sin_concesion", ACTOR)


@pytest.mark.parametrize("adaptador", [InventoryMaterialReservationAdapter,
                                       CanonicalProductionConsumptionAdapter,
                                       CanonicalProductionReceiptAdapter])
def test_the_runtime_adapters_carry_the_delegated_grant(adaptador):
    import sqlite3

    instancia = adaptador(sqlite3.connect(":memory:"), branch_id=new_uuid(),
                          warehouse_id=new_uuid(), actor_user_id=ACTOR, document_id=new_uuid())
    checker = instancia.policy._checker
    assert type(checker).__name__ == "DelegatedIntegrationPermissionChecker"
    assert not checker.has_permission(ACTOR, InventoryPermissions.ADJUSTMENT_CREATE)
