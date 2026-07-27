import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.delivery_ui_filters import (
    infer_workflow_for_ui,
    matches_operational_tab,
    matches_scheduled_window,
)


def test_infer_workflow_for_ui_legacy_cases():
    assert infer_workflow_for_ui({"delivery_type": "pickup"}) == "counter"
    assert infer_workflow_for_ui({"estado": "programado"}) == "scheduled"
    assert infer_workflow_for_ui({"scheduled_at": "2026-05-25T10:00:00"}) == "scheduled"
    assert infer_workflow_for_ui({"estado": "pendiente"}) == "delivery"


def test_matches_operational_tab_combined_cases():
    counter = {"estado": "pendiente", "delivery_type": "sucursal"}
    scheduled = {"estado": "pendiente", "scheduled_at": "2026-05-25T10:00:00"}
    delivery = {"estado": "preparacion", "workflow_type": ""}
    historial = {"estado": "entregado"}
    ajustes = {"estado": "pendiente", "adjustment_pending": 1}

    assert matches_operational_tab(counter, "counter")
    assert not matches_operational_tab(counter, "delivery")
    assert matches_operational_tab(scheduled, "scheduled")
    assert matches_operational_tab(delivery, "delivery")
    assert matches_operational_tab(historial, "historial")
    assert matches_operational_tab(ajustes, "ajustes")


def test_matches_scheduled_window_ranges():
    now = datetime.now()
    p_today = {"scheduled_at": now.isoformat()}
    p_tomorrow = {"scheduled_at": (now + timedelta(days=1)).isoformat()}
    p_month = {"scheduled_at": (now + timedelta(days=20)).isoformat()}
    p_out = {"scheduled_at": (now + timedelta(days=45)).isoformat()}

    assert matches_scheduled_window(p_today, "today")
    assert matches_scheduled_window(p_tomorrow, "tomorrow")
    assert matches_scheduled_window(p_month, "month")
    assert not matches_scheduled_window(p_out, "month")

