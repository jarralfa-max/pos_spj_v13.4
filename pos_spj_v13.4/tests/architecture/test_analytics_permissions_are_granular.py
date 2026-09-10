from pathlib import Path

from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


ROOT = Path(__file__).resolve().parents[2]


def test_analytics_reuses_the_canonical_inteligencia_bi_module_key():
    """§3/§64: one canonical route per functional area — no parallel module
    key for the BI sidebar entry (interfaz/menu_lateral.py: "Inteligencia de
    Negocios" → "INTELIGENCIA_BI")."""
    assert "INTELIGENCIA_BI" in CANONICAL_MODULE_PERMISSIONS
    assert "ANALYTICS" not in CANONICAL_MODULE_PERMISSIONS
    assert "BUSINESS_INTELLIGENCE" not in CANONICAL_MODULE_PERMISSIONS
    assert "FORECASTING" not in CANONICAL_MODULE_PERMISSIONS
    assert "DECISION_INTELLIGENCE" not in CANONICAL_MODULE_PERMISSIONS


def test_inteligencia_bi_catalog_entry_grew_past_the_old_flat_stub():
    actions = CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"]
    assert len(actions) > 60
    assert "forecast.modelo.aprobar" in actions
    assert "recomendacion.aprobar" in actions
    assert "escenario.crear" in actions
    assert "alerta_regla.activar" in actions
    # the pre-BI-2 flat legacy codes must still be present (back-compat)
    for legacy in ("ver", "ver_ventas", "ver_finanzas", "exportar", "configurar"):
        assert legacy in actions


def test_analytics_domain_never_imports_legacy_forecast_engines():
    domain_dir = ROOT / "backend/domain/analytics"
    application_dir = ROOT / "backend/application/analytics"
    forbidden = (
        "core.services.forecast_engine",
        "core.services.forecast_service",
        "core.services.actionable_forecast",
        "core.forecast.demand_forecast_engine",
        "core.forecast.replenishment_engine",
        "core.services.enterprise.demand_forecasting",
        "core.services.ceo_dashboard",
        "core.services.decision_engine",
        "core.services.alert_engine",
        "modulos.reportes_bi_v2",
    )
    for path in list(domain_dir.rglob("*.py")) + list(application_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"{path} references legacy module {needle}"
