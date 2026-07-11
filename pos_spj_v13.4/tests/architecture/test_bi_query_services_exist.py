"""FASE 13 — el query layer de BI existe y expone el contrato esperado."""
import importlib


def test_bi_query_services_importables():
    mods = [
        "backend.application.queries.bi_dashboard_query_service",
        "backend.application.queries.bi_sales_query_service",
        "backend.application.queries.bi_inventory_query_service",
        "backend.application.queries.bi_finance_query_service",
        "backend.application.queries.bi_forecast_query_service",
        "backend.application.services.bi_dashboard_service",
        "backend.application.dto.bi_dashboard_dto",
    ]
    for m in mods:
        importlib.import_module(m)


def test_dashboard_service_expone_build_dashboard():
    from backend.application.services.bi_dashboard_service import BiDashboardService
    assert hasattr(BiDashboardService, "build_dashboard")


def test_dto_payload_contract():
    from backend.application.dto.bi_dashboard_dto import DashboardPayload
    fields = DashboardPayload.__dataclass_fields__
    for key in ("filters", "kpis", "charts", "highlights", "alerts",
                "predictions", "insights", "allowed_sections"):
        assert key in fields
