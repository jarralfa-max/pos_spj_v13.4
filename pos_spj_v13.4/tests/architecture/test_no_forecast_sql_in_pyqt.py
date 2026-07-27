"""Planeación de Compras / Forecast: prohibido SQL directo en PyQt.

Las lecturas van por PurchasePlanningReadService; el pronóstico va por
ForecastService con identidades UUID string.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT, SQL_RE, collect_regex_violations

EXECUTE_RE = re.compile(r"\.execute\s*\(|\.executemany\s*\(|\.cursor\s*\(")

PLANNING_UI = (APP_ROOT / "modulos" / "planeacion_compras.py",)


def test_no_forecast_sql_in_pyqt() -> None:
    violations = collect_regex_violations(pattern=SQL_RE, roots=PLANNING_UI)
    violations += collect_regex_violations(pattern=EXECUTE_RE, roots=PLANNING_UI)
    assert not violations, (
        "SQL directo en modulos/planeacion_compras.py:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )


def test_planning_ui_uses_query_service() -> None:
    text = (APP_ROOT / "modulos" / "planeacion_compras.py").read_text(encoding="utf-8")
    assert "PurchasePlanningReadService" in text
