"""SDLC-CORE-001: la falla de cablear un contexto no apaga a los demás y se ve.

Antes todo se armaba en un solo literal de diccionario: si un `wire_*` lanzaba, los
siguientes no se suscribían, los despachos de arranque no corrían y `app.py` sólo
dejaba una línea en el log.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.health.health_status import (  # noqa: E402
    HealthCheckResult,
    HealthReport,
    HealthStatus,
)
from backend.bootstrap.wiring import event_wiring  # noqa: E402
from backend.shared.events.application_bus import reset_bus  # noqa: E402
from frontend.desktop.shell.application_shell.status_bar import StatusBar  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _bus_aislado():
    reset_bus()
    yield
    reset_bus()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    yield c
    c.close()


def _falla(*_args, **_kwargs):
    raise RuntimeError("cableado roto")


def _romper_precios(monkeypatch):
    from backend.application.pricing.integrations import wiring
    monkeypatch.setattr(wiring, "wire_pricing", _falla)


def test_a_failing_context_does_not_stop_the_following_ones(conn, monkeypatch):
    _romper_precios(monkeypatch)

    summary = event_wiring.wire_cross_context_events(conn)

    assert summary["pricing"]["count"] == 0
    assert summary["procurement"]["count"] > 0                 # antes del que falla
    assert summary["costing"]["count"] > 0                     # después
    assert summary["hr"]["count"] > 0
    fallas = event_wiring.wiring_failures(summary)
    assert "pricing" in fallas and "costing" not in fallas


def test_the_first_context_failing_leaves_the_rest_wired(conn, monkeypatch):
    from backend.application.finance import wiring
    monkeypatch.setattr(wiring, "wire_finance", _falla)

    summary = event_wiring.wire_cross_context_events(conn)

    assert "finance" in event_wiring.wiring_failures(summary)
    assert summary["procurement"]["count"] > 0


def test_startup_dispatches_still_run_after_a_wiring_failure(conn, monkeypatch):
    from backend.application.cash_register import finance_wiring
    _romper_precios(monkeypatch)
    despachos = []
    monkeypatch.setattr(finance_wiring, "dispatch_cash_outbox",
                        lambda connection, bus, **k: despachos.append(connection) or {})

    event_wiring.wire_cross_context_events(conn)

    assert despachos == [conn]


def test_a_failed_dispatch_is_reported_too(conn, monkeypatch):
    from backend.application.cash_register import finance_wiring
    monkeypatch.setattr(finance_wiring, "dispatch_cash_outbox", _falla)

    summary = event_wiring.wire_cross_context_events(conn)

    assert "cash_outbox" in event_wiring.wiring_failures(summary)


def test_a_failure_leaves_a_structured_log_record(conn, monkeypatch, caplog):
    _romper_precios(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="spj.bootstrap.event_wiring"):
        event_wiring.wire_cross_context_events(conn)
    (registro,) = [r for r in caplog.records if getattr(r, "wiring_step", "") == "pricing"]
    assert registro.exc_info is not None


def test_a_plain_summary_has_no_failures():
    assert event_wiring.wiring_failures({}) == {}


# ── salud ───────────────────────────────────────────────────────────────────
def _reporte() -> HealthReport:
    return HealthReport(
        overall_status=HealthStatus.HEALTHY, generated_at=datetime.now(timezone.utc),
        checks=(HealthCheckResult("database", HealthStatus.HEALTHY),))


def test_a_failure_degrades_the_health_report():
    reporte = event_wiring.with_wiring_health(_reporte(), {"pricing": "cableado roto"})
    assert reporte.overall_status is HealthStatus.DEGRADED
    (fallo,) = reporte.failing_checks()
    assert fallo.check_name == event_wiring.WIRING_HEALTH_CHECK
    assert "pricing" in fallo.message


def test_no_failures_leave_the_report_alone():
    original = _reporte()
    assert event_wiring.with_wiring_health(original, {}) is original


def test_a_worse_status_is_not_improved():
    enfermo = HealthReport(overall_status=HealthStatus.UNHEALTHY, checks=(),
                           generated_at=datetime.now(timezone.utc))
    reporte = event_wiring.with_wiring_health(enfermo, {"pricing": "x"})
    assert reporte.overall_status is HealthStatus.UNHEALTHY


# ── aviso en el shell ───────────────────────────────────────────────────────
def test_the_status_bar_shows_the_warning(qapp):
    barra = StatusBar()
    assert barra.integration_warning_text == ""

    barra.set_integration_warning(event_wiring.wiring_warning({"pricing": "x", "hr": "y"}))

    assert "Integración" in barra.integration_warning_text
    assert "pricing" in barra.integration_warning_tooltip
    assert "hr" in barra.integration_warning_tooltip


def test_no_failures_show_no_warning(qapp):
    barra = StatusBar()
    barra.set_integration_warning(event_wiring.wiring_warning({}))
    assert barra.integration_warning_text == ""


def test_the_app_survives_and_reports_an_unexpected_wiring_crash(monkeypatch, conn):
    from frontend.desktop import app
    monkeypatch.setattr(event_wiring, "wire_cross_context_events", _falla)
    assert app._wire_events(conn) == {"event_wiring": "cableado roto"}


def test_the_app_reports_the_failures_of_each_context(monkeypatch, conn):
    from frontend.desktop import app
    _romper_precios(monkeypatch)
    assert "pricing" in app._wire_events(conn)
