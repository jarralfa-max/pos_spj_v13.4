"""BI-14 guardrail — the ForecastingPlatform must never import
TreasuryService/Treasury concretely.

BI-0 found `core/services/actionable_forecast.py` and
`core/services/decision_engine.py` calling `treasury_service.*` directly —
exactly the cross-context coupling §10 forbids ("BI no debe depender directo
de TreasuryService"). BI-14 fixed this properly for purchase planning via
`FinanceQueryPort` (`backend/domain/forecasting/integration_ports.py`); this
test makes sure it stays fixed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN_NEEDLES = (
    "treasury_service",
    "TreasuryService",
    "core.services.finance",
    "core.services.decision_engine",
    "core.services.actionable_forecast",
)


def test_forecasting_domain_and_application_never_import_treasury():
    domain_dir = ROOT / "backend/domain/forecasting"
    application_dir = ROOT / "backend/application/forecasting"
    for path in list(domain_dir.rglob("*.py")) + list(application_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_NEEDLES:
            assert needle not in source, f"{path} references forbidden {needle}"
