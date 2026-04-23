from pathlib import Path


def test_finanzas_unificadas_tiene_auto_refresh_kpis():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    assert 'def _wire_kpi_auto_refresh' in src
    assert 'self._kpi_timer.setInterval(15000)' in src
    assert 'def _refresh_kpis_if_dashboard_visible' in src


def test_finanzas_unificadas_suscribe_eventos_kpi():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    assert '"VENTA_COMPLETADA"' in src
    assert '"MOVIMIENTO_FINANCIERO"' in src
    assert 'self._cargar_dashboard_financiero' in src


def test_finanzas_dashboard_usa_claves_reales_tesoreria():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    assert "cxp_pendiente" in src
    assert "cxc_pendiente" in src
    assert "margen_neto_pct" in src


def test_finanzas_safe_text_helper_presente():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    assert "def _safe_text" in src
    assert "currentText" in src
