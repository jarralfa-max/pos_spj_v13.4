"""Single source of truth mapping canonical inventory permissions to display
capabilities (§15).

Every inventory presenter/page should resolve its ``InventoryCapabilities``
here instead of calling ``InventoryPermissions`` checks ad hoc, so the module
never drifts into two different permission→capability mappings (mirrors
``frontend/desktop/modules/purchasing/capability_resolver.py``).
"""

from __future__ import annotations

from typing import Callable

from backend.application.inventory.permissions import InventoryPermissions
from frontend.desktop.modules.inventory.view_models import InventoryCapabilities


def resolve_inventory_capabilities(can: Callable[[str], bool]) -> InventoryCapabilities:
    P = InventoryPermissions
    return InventoryCapabilities(
        module_view=can(P.VIEW),

        warehouse_view=can(P.WAREHOUSE_VIEW),
        warehouse_create=can(P.WAREHOUSE_CREATE),
        warehouse_edit=can(P.WAREHOUSE_EDIT),
        warehouse_activate=can(P.WAREHOUSE_ACTIVATE),
        warehouse_block=can(P.WAREHOUSE_BLOCK),
        warehouse_deactivate=can(P.WAREHOUSE_DEACTIVATE),

        location_view=can(P.LOCATION_VIEW),
        location_manage=can(P.LOCATION_MANAGE),

        lot_view=can(P.LOT_VIEW),
        lot_create=can(P.LOT_CREATE),
        lot_edit=can(P.LOT_EDIT),
        lot_block=can(P.LOT_BLOCK),
        lot_release=can(P.LOT_RELEASE),
        lot_print=can(P.LABEL_PRINT),
        lot_reprint=can(P.LABEL_REPRINT),

        weight_capture=can(P.WEIGHT_CAPTURE),
        weight_manual_override=can(P.WEIGHT_MANUAL_OVERRIDE),
        scale_use=can(P.SCALE_USE),
        scale_manage=can(P.SCALE_MANAGE),

        temperature_view=can(P.TEMPERATURE_VIEW),
        temperature_record=can(P.TEMPERATURE_RECORD),
        temperature_resolve=can(P.TEMPERATURE_RESOLVE),

        reservation_view=can(P.RESERVATION_VIEW),
        reservation_create=can(P.RESERVATION_CREATE),
        reservation_release=can(P.RESERVATION_RELEASE),

        movement_view=can(P.MOVEMENT_VIEW),
        movement_manual=can(P.MOVEMENT_CREATE),
        movement_reverse=can(P.MOVEMENT_REVERSE),

        in_transit_view=can(P.IN_TRANSIT_VIEW),

        receipt_view=can(P.RECEIPT_VIEW),
        receipt_inspect=can(P.RECEIPT_INSPECT),
        receipt_reverse=can(P.RECEIPT_REVERSE),

        count_view=can(P.COUNT_VIEW),
        count_create=can(P.COUNT_CREATE),
        count_execute=can(P.COUNT_EXECUTE),
        count_confirm=can(P.COUNT_CONFIRM),
        count_recount=can(P.COUNT_RECOUNT),
        count_approve=can(P.COUNT_APPROVE),
        count_view_expected=can(P.COUNT_VIEW_EXPECTED),

        adjustment_view=can(P.ADJUSTMENT_VIEW),
        adjustment_create=can(P.ADJUSTMENT_CREATE),
        adjustment_approve=can(P.ADJUSTMENT_APPROVE),
        adjustment_post=can(P.ADJUSTMENT_POST),
        adjustment_reverse=can(P.ADJUSTMENT_REVERSE),

        quarantine_view=can(P.QUARANTINE_VIEW),
        quarantine_create=can(P.QUARANTINE_CREATE),
        quarantine_release=can(P.QUARANTINE_RELEASE),
        quarantine_dispose=can(P.DISPOSAL_AUTHORIZE),
        quality_block=can(P.QUALITY_BLOCK),
        quality_release=can(P.QUALITY_RELEASE),

        replenishment_view=can(P.REPLENISHMENT_VIEW),
        replenishment_manage=can(P.REPLENISHMENT_MANAGE),
        replenishment_generate=can(P.REPLENISHMENT_GENERATE),

        traceability_view=can(P.VIEW_TRACEABILITY),
        audit_view=can(P.VIEW_AUDIT),
        export=can(P.EXPORT),

        settings_view=can(P.SETTINGS_VIEW),
        settings_manage=can(P.SETTINGS_MANAGE),
        notifications_manage=can(P.NOTIFICATIONS_MANAGE),
        whatsapp_alerts_manage=can(P.WHATSAPP_ALERTS_MANAGE),
    )
