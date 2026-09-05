"""BI-1 — ratchet: no new parallel forecasting engine.

BI-0 (`docs/refactor/BI-0_legacy_audit.md`) found **five** independent
forecast-algorithm implementations, three of them wired live simultaneously
in `app_container.py`. The master-prompt rule (§16/§144) is "una sola
ForecastingPlatform" — none of the legacy engines below can be deleted yet
(no canonical replacement exists), but this guardrail freezes the set so a
**sixth** engine can't be added silently while the canonical
`backend/application/forecasting/` platform is being built (BI-7+).

The allowlist only shrinks: when a legacy engine is replaced by the
canonical platform and deleted, remove it here. If this test fails because a
*new* class was added, that is very likely an unintended duplicate forecast
engine — implement it inside the canonical platform instead.

`backend/domain/forecasting/` and `backend/application/forecasting/` (the
canonical platform itself, BI-7+) are excluded from the scan — it is
expected and correct for that platform to keep growing classes named things
like `InventoryForecastService`/`PurchasePlanningService`; this guardrail
watches for a *duplicate* appearing outside it, not the platform's own
growth (confirmed BI-16: `InventoryForecastService` initially tripped the
naive scan before this exclusion was added).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# Forecast/replenishment "engine-shaped" class name pattern: something that
# owns a `forecast_*`/`generar_*`/`run`/`analisis_demanda` style public API
# for demand/replenishment prediction. Matched by class name only — cheap
# and precise enough given the small, known universe of hits.
_ENGINE_CLASS_NAME = re.compile(
    r"^(.*Forecast(ing)?Engine.*|.*ForecastService.*|ReplenishmentEngine|"
    r"SafetyStockCalculator|SeasonalityDetector|ActionableForecastService|"
    r"DemandForecastingEngine)$"
)

_SCAN_DIRS = ("core", "backend", "modulos")

# The canonical platform (BI-7+) lives here and is EXPECTED to keep growing
# service classes with "Forecast"/"Service" in their names
# (`InventoryForecastService`, `PurchasePlanningService`, ...) — this
# guardrail watches for a *duplicate* engine appearing outside the canonical
# platform, not for the platform's own legitimate growth.
_EXCLUDED_PREFIXES = ("backend/domain/forecasting/", "backend/application/forecasting/")


def _current_engine_classes() -> set[str]:
    hits: set[str] = set()
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(_ROOT).as_posix()
            if "__pycache__" in path.parts or "/tests/" in path.as_posix():
                continue
            if rel.startswith(_EXCLUDED_PREFIXES):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and _ENGINE_CLASS_NAME.match(node.name):
                    hits.add(f"{path.relative_to(_ROOT).as_posix()}::{node.name}")
    return hits


# Frozen at BI-1 (2026-09-04) — see BI-0 audit's forecast parity matrix.
# SÓLO puede reducirse: cuando el motor se retire (BI-32) tras existir el
# reemplazo canónico con paridad de tests, se borra de aquí.
_ALLOWLIST: frozenset[str] = frozenset({
    "core/services/forecast_engine.py::ForecastEngine",
    "core/services/forecast_service.py::ForecastService",
    "core/services/actionable_forecast.py::ActionableForecastService",
    "core/forecast/demand_forecast_engine.py::DemandForecastEngine",
    "core/forecast/seasonality_detector.py::SeasonalityDetector",
    "core/forecast/replenishment_engine.py::ReplenishmentEngine",
    "core/forecast/safety_stock_calculator.py::SafetyStockCalculator",
    "core/services/enterprise/demand_forecasting.py::DemandForecastingEngine",
})


def test_no_new_forecast_engine_was_added_outside_the_frozen_allowlist():
    current = _current_engine_classes()
    new = current - _ALLOWLIST
    assert not new, (
        "New forecast-engine-shaped class(es) detected outside the BI-1 "
        f"allowlist: {sorted(new)}. Implement forecasting logic inside the "
        "canonical backend/application/forecasting/ platform (BI-7+) instead "
        "of adding another parallel engine."
    )


def test_allowlist_entries_still_exist_or_were_intentionally_retired():
    """Sanity check: every allowlisted hit should still resolve today. If one
    disappears because the file was deleted/renamed during a later BI phase,
    remove it from `_ALLOWLIST` in the same change — don't leave stale
    entries masking a real removal."""
    current = _current_engine_classes()
    stale = _ALLOWLIST - current
    assert not stale, (
        f"Allowlist entries no longer found in the codebase: {sorted(stale)}. "
        "Remove them from _ALLOWLIST as part of the change that retired them."
    )
