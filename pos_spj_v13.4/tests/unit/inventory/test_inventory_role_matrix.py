"""INV-1 (§14, §64) — closure matrix: inventory routes/actions stay
least-privilege by role.

Mirrors ``tests/unit/procurement/test_purchasing_role_matrix.py`` /
``test_permission_migration_role_scenarios.py``. For each of the ten
canonical inventory roles this checks:

  1. the sidebar sections ``visible_entries()`` returns match exactly the
     entries whose declared permission the role holds (catches the §16
     wiring gap: a ``visible_entries()`` nobody calls is not a control);
  2. sensitive capabilities are never inferred from read-only access
     (segregation of duties: counters don't approve, dispatchers/receivers
     don't self-authorize the other side, auditors never mutate);
  3. backend (`InventorySessionPermissionChecker`) and UI
     (`session.tiene_permiso`) agree on every grant/denial;
  4. an inactive session or one without an active branch fails closed even
     when the role would otherwise grant the permission.
"""

from __future__ import annotations

import pytest

from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.session_authorization import (
    InventorySessionPermissionChecker,
)
from frontend.desktop.modules.inventory.capability_resolver import (
    resolve_inventory_capabilities,
)
from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV, visible_entries

P = InventoryPermissions

ROLE_GRANTS = {
    "solo_lectura": {
        P.VIEW, P.WAREHOUSE_VIEW, P.LOCATION_VIEW, P.LOT_VIEW,
        P.MOVEMENT_VIEW, P.RESERVATION_VIEW, P.IN_TRANSIT_VIEW,
    },
    "almacenista": {
        P.VIEW, P.WAREHOUSE_VIEW, P.LOCATION_VIEW, P.LOT_VIEW, P.LOT_CREATE,
        P.MOVEMENT_VIEW, P.RESERVATION_VIEW, P.RESERVATION_CREATE,
        P.RESERVATION_RELEASE, P.IN_TRANSIT_VIEW,
        P.COUNT_VIEW, P.COUNT_EXECUTE, P.COUNT_CONFIRM,
        P.WEIGHT_CAPTURE, P.SCALE_USE, P.LABEL_PRINT,
    },
    "receptor": {
        P.RECEIPT_VIEW, P.RECEIPT_INSPECT, P.LOT_VIEW, P.LOT_CREATE,
        P.WEIGHT_CAPTURE, P.TEMPERATURE_VIEW, P.TEMPERATURE_RECORD,
        P.QUARANTINE_VIEW, P.QUARANTINE_CREATE,
    },
    "contador_fisico": {
        P.COUNT_VIEW, P.COUNT_CREATE, P.COUNT_EXECUTE, P.COUNT_CONFIRM,
        P.COUNT_RECOUNT,
    },
    "aprobador_conteos": {P.COUNT_VIEW, P.COUNT_APPROVE},
    "ajustador_inventario": {P.ADJUSTMENT_VIEW, P.ADJUSTMENT_CREATE},
    "aprobador_ajustes": {
        P.ADJUSTMENT_VIEW, P.ADJUSTMENT_APPROVE, P.ADJUSTMENT_POST,
    },
    "calidad": {
        P.QUARANTINE_VIEW, P.QUARANTINE_CREATE, P.QUARANTINE_RELEASE,
        P.DISPOSAL_AUTHORIZE, P.QUALITY_BLOCK, P.QUALITY_RELEASE,
        P.TEMPERATURE_VIEW, P.TEMPERATURE_RESOLVE,
    },
    "auditor_inventario": {
        P.VIEW, P.VIEW_ALL_BRANCHES, P.VIEW_TRACEABILITY, P.VIEW_AUDIT,
        P.EXPORT,
    },
    "administrador_inventario": {
        P.SETTINGS_VIEW, P.SETTINGS_MANAGE, P.WAREHOUSE_VIEW,
        P.WAREHOUSE_CREATE, P.WAREHOUSE_EDIT, P.WAREHOUSE_ACTIVATE,
        P.WAREHOUSE_BLOCK, P.WAREHOUSE_DEACTIVATE, P.LOCATION_VIEW,
        P.LOCATION_MANAGE, P.NOTIFICATIONS_MANAGE, P.WHATSAPP_ALERTS_MANAGE,
        P.SCALE_MANAGE,
    },
}


class _Session:
    user_id = "role-user"
    active_branch_id = "branch-1"

    def __init__(self, grants, *, is_active=True, active_branch_id="branch-1"):
        self._grants = set(grants)
        self.is_active = is_active
        self.active_branch_id = active_branch_id

    def tiene_permiso(self, code):
        return code in self._grants


def _capabilities(role):
    return resolve_inventory_capabilities(_Session(ROLE_GRANTS[role]).tiene_permiso)


@pytest.mark.parametrize("role", sorted(ROLE_GRANTS))
def test_visible_entries_match_declared_permission_exactly(role):
    grants = ROLE_GRANTS[role]
    expected = {e.page_id for e in INVENTORY_NAV if e.permission in grants}
    actual = {e.page_id for e in visible_entries(_Session(grants).tiene_permiso)}
    assert actual == expected


def test_user_without_module_view_sees_only_permission_specific_sections():
    # Sections are gated individually, not behind one umbrella "module_view" —
    # a role can see e.g. Recepciones without INVENTARIO.ver (§16's contract is
    # per-section, not all-or-nothing). Confirm the truly empty case denies all.
    assert visible_entries(_Session(set()).tiene_permiso) == ()


def test_contador_fisico_cannot_approve_own_count():
    caps = _capabilities("contador_fisico")
    assert caps.count_execute and caps.count_confirm and caps.count_recount
    assert not caps.count_approve


def test_aprobador_conteos_cannot_capture():
    caps = _capabilities("aprobador_conteos")
    assert caps.count_approve
    assert not caps.count_execute and not caps.count_create


def test_ajustador_cannot_approve_or_post_own_adjustment():
    caps = _capabilities("ajustador_inventario")
    assert caps.adjustment_create
    assert not caps.adjustment_approve and not caps.adjustment_post


def test_aprobador_ajustes_cannot_create():
    caps = _capabilities("aprobador_ajustes")
    assert caps.adjustment_approve and caps.adjustment_post
    assert not caps.adjustment_create


def test_receptor_cannot_dispose_or_release_quarantine():
    caps = _capabilities("receptor")
    assert caps.quarantine_create
    assert not caps.quarantine_release and not caps.quarantine_dispose


def test_calidad_can_release_and_dispose():
    caps = _capabilities("calidad")
    assert caps.quarantine_release and caps.quarantine_dispose
    assert caps.quality_block and caps.quality_release


def test_auditor_has_zero_mutation_capabilities():
    caps = _capabilities("auditor_inventario")
    assert caps.module_view and caps.traceability_view and caps.audit_view and caps.export
    mutation_fields = (
        "warehouse_create", "warehouse_edit", "warehouse_activate", "warehouse_block",
        "warehouse_deactivate",
        "location_manage", "lot_create", "lot_edit", "lot_block", "lot_release",
        "weight_capture", "weight_manual_override", "movement_manual", "movement_reverse",
        "count_create", "count_execute", "count_confirm", "count_approve",
        "adjustment_create", "adjustment_approve", "adjustment_post", "adjustment_reverse",
        "quarantine_create", "quarantine_release", "quarantine_dispose",
        "quality_block", "quality_release", "replenishment_manage", "settings_manage",
    )
    for field in mutation_fields:
        assert getattr(caps, field) is False, field


def test_administrador_inventario_does_not_imply_financial_approval_or_sod_bypass():
    caps = _capabilities("administrador_inventario")
    assert caps.warehouse_create and caps.settings_manage
    assert caps.warehouse_deactivate  # explicitly granted, not inferred from block/edit
    # §14: configuring the module never implies approving counts/adjustments —
    # those are separate, deliberately-granted roles.
    assert not caps.adjustment_approve
    assert not caps.count_approve
    assert not caps.quarantine_release


@pytest.mark.parametrize("role", sorted(ROLE_GRANTS))
def test_backend_and_ui_authorization_agree(role):
    grants = ROLE_GRANTS[role]
    session = _Session(grants)
    checker = InventorySessionPermissionChecker(session)
    for code in (P.VIEW, P.ADJUSTMENT_APPROVE, P.COUNT_APPROVE, P.QUARANTINE_RELEASE,
                 P.WAREHOUSE_CREATE, P.WAREHOUSE_DEACTIVATE):
        granted = code in grants
        assert session.tiene_permiso(code) == granted
        assert checker.has_permission(session.user_id, code) == granted


def test_session_without_active_branch_fails_closed_despite_grant():
    session = _Session({P.ADJUSTMENT_APPROVE}, active_branch_id="")
    assert session.tiene_permiso(P.ADJUSTMENT_APPROVE)  # UI-side: concede
    checker = InventorySessionPermissionChecker(session)
    assert not checker.has_permission(session.user_id, P.ADJUSTMENT_APPROVE)


def test_inactive_session_fails_closed_despite_grant():
    session = _Session({P.ADJUSTMENT_APPROVE}, is_active=False)
    checker = InventorySessionPermissionChecker(session)
    assert not checker.has_permission(session.user_id, P.ADJUSTMENT_APPROVE)
