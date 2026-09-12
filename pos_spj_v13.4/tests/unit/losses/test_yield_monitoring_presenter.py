"""La página de Rendimientos de Mermas (PASS 6).

`losses_yields` abría un placeholder mientras `YieldMonitoringQueryService`
existía Y `losses_factory.py` ya lo construía y lo dejaba en su mapa de
servicios. Faltaba sólo el puente y la pantalla.

Las pruebas van contra el PRESENTADOR y no contra la base: lo que hay que fijar
es el cálculo —qué cuenta como grave, cuál es la peor desviación, cómo se
formatea una diferencia con signo— y eso no necesita SQL. El servicio se
sustituye por uno falso que devuelve exactamente lo que devuelve el real.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.losses.yield_queries import YieldAlertView, YieldVarianceView
from frontend.desktop.modules.losses.presenters.yield_monitoring_presenter import (
    YieldMonitoringPresenter,
)

SUCURSAL = "b-1"


class _Contexto:
    active_branch_id = SUCURSAL


class _ConsultaFalsa:
    """Devuelve lo que devuelve el servicio real: tuplas de vistas."""

    def __init__(self, variances=(), alerts=()):
        self._variances = tuple(variances)
        self._alerts = tuple(alerts)
        self.pedidos: list[tuple[str, str, int]] = []

    def recent_variances(self, *, branch_id, limit=100):
        self.pedidos.append(("variances", branch_id, limit))
        return self._variances

    def open_alerts(self, *, branch_id, limit=100):
        self.pedidos.append(("alerts", branch_id, limit))
        return self._alerts


def _variance(*, pct="−0", cantidad="0", severidad="LOW", esperado="10", real="10"):
    return YieldVarianceView(
        id="v1", production_id="prod-12345678", product_id="art-87654321",
        expected_output=Decimal(esperado), actual_output=Decimal(real),
        variance_quantity=Decimal(cantidad), variance_pct=Decimal(pct),
        severity=severidad, detected_at="2026-09-11T08:30:00")


def _alert(*, severidad="HIGH", esperado="95", real="88", bajo="90", alto="100"):
    return YieldAlertView(
        id="a1", variance_id="v1", severity=severidad,
        expected_yield_pct=Decimal(esperado), actual_yield_pct=Decimal(real),
        lower_tolerance_pct=Decimal(bajo), upper_tolerance_pct=Decimal(alto),
        message="Rendimiento bajo tolerancia", created_at="2026-09-11T09:00:00")


def _presentador(**kwargs):
    return YieldMonitoringPresenter(_ConsultaFalsa(**kwargs), _Contexto)


# ── la sucursal ─────────────────────────────────────────────────────────────
def test_both_reads_are_scoped_to_the_active_branch():
    """Sin el filtro de sucursal la pantalla enseña desviaciones de plantas
    ajenas y parece que funciona."""
    consulta = _ConsultaFalsa()
    presentador = YieldMonitoringPresenter(consulta, _Contexto)
    presentador.variances()
    presentador.open_alerts()
    assert [p[1] for p in consulta.pedidos] == [SUCURSAL, SUCURSAL]


def test_a_session_without_branch_asks_for_an_empty_one_instead_of_crashing():
    """Arrancar sin sucursal activa es un estado real (antes de elegirla)."""
    consulta = _ConsultaFalsa()
    YieldMonitoringPresenter(consulta, lambda: object()).variances()
    assert consulta.pedidos[0][1] == ""


# ── filas ───────────────────────────────────────────────────────────────────
def test_the_difference_carries_its_sign():
    """Producir de MENOS y de MÁS son problemas distintos; sin signo, la
    columna no distingue cuál de los dos ocurrió."""
    filas = _presentador().variance_rows([
        _variance(cantidad="-2.5", pct="-12.5"),
        _variance(cantidad="3", pct="7.25"),
    ])
    assert [f[4] for f in filas] == ["-2.500", "+3.000"]
    assert [f[5] for f in filas] == ["-12.50%", "+7.25%"]


def test_an_alert_shows_the_tolerated_range_next_to_the_real_yield():
    """Un 88% no dice nada solo: lo que importa es contra qué rango se compara."""
    fila = _presentador().alert_rows([_alert(real="88", bajo="90", alto="100")])[0]
    assert fila[2] == "88.00%"
    assert fila[3] == "90.00% – 100.00%"


def test_an_alert_without_message_shows_a_dash_not_an_empty_cell():
    """Una celda vacía se lee como "no cargó"; un guion dice "no hay texto"."""
    from dataclasses import replace

    fila = _presentador().alert_rows([replace(_alert(), message="")])[0]
    assert fila[4] == "—"


# ── tarjetas ────────────────────────────────────────────────────────────────
def test_only_the_severities_the_domain_calls_serious_are_counted():
    """Se cuentan CRITICAL y HIGH. Si se contaran todas, el indicador de graves
    coincidiría siempre con el de alertas abiertas y no diría nada."""
    tarjetas = _presentador().kpi_cards(
        [], [_alert(severidad="CRITICAL"), _alert(severidad="HIGH"),
             _alert(severidad="LOW"), _alert(severidad="MEDIUM")])
    valores = {t.key: t.value for t in tarjetas}
    assert valores["alerts"] == "4"
    assert valores["critical"] == "2"


def test_the_worst_variance_is_the_biggest_in_absolute_value():
    """Producir de MÁS también es una desviación —sobra materia, el estándar
    está mal, o alguien registró mal—. Ordenar por el número con signo dejaría
    fuera la mitad de los casos: aquí +30 es peor que −12."""
    tarjetas = _presentador().kpi_cards(
        [_variance(pct="-12"), _variance(pct="30"), _variance(pct="5")], [])
    assert {t.key: t.value for t in tarjetas}["worst"] == "+30.00%"


def test_no_alerts_is_reported_as_good_not_as_neutral():
    variantes = {t.key: t.variant for t in _presentador().kpi_cards([], [])}
    assert variantes["alerts"] == "success"
    assert variantes["critical"] == "success"


def test_an_empty_period_shows_a_dash_instead_of_a_fake_zero():
    """Un "0.00%" diría que se midió y no hubo desviación. No se midió nada."""
    assert {t.key: t.value for t in _presentador().kpi_cards([], [])}["worst"] == "—"


# ── la pantalla ─────────────────────────────────────────────────────────────
def test_the_page_loads_both_tables(qapp):
    from frontend.desktop.modules.losses.pages.yield_monitoring_page import (
        YieldMonitoringPage,
    )

    presentador = YieldMonitoringPresenter(
        _ConsultaFalsa(variances=[_variance(pct="-4")], alerts=[_alert()]), _Contexto)
    pagina = YieldMonitoringPage(presentador)
    pagina.ensure_loaded()

    assert pagina.variances.rowCount() == 1
    assert pagina.alerts.rowCount() == 1


def test_the_page_does_not_query_until_it_is_opened(qapp):
    """Construir el módulo no puede pagar dos consultas por una pantalla que
    quizá nadie abra."""
    from frontend.desktop.modules.losses.pages.yield_monitoring_page import (
        YieldMonitoringPage,
    )

    consulta = _ConsultaFalsa()
    YieldMonitoringPage(YieldMonitoringPresenter(consulta, _Contexto))
    assert consulta.pedidos == []


@pytest.fixture
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
