from pathlib import Path

# Remediación E: los KPIs de finanzas se refrescan por EVENTOS; el timer queda
# como red de seguridad de baja frecuencia (>=60 s), no como mecanismo primario.


def test_finanzas_unificadas_tiene_auto_refresh_kpis():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    assert 'def _wire_kpi_auto_refresh' in src
    # El timer es fallback de baja frecuencia (>=60 s); antes 15 s disimulaba
    # la falta de eventos.
    assert 'self._kpi_timer.setInterval(60000)' in src
    assert 'def _refresh_kpis_if_visible' in src


def test_finanzas_unificadas_suscribe_eventos_kpi():
    src = Path('modulos/finanzas_unificadas.py').read_text(encoding='utf-8')
    # Refresh en caliente por eventos canónicos (no por timer).
    assert '"VENTA_COMPLETADA"' in src
    assert '"MOVIMIENTO_FINANCIERO"' in src
    # El corte Z / movimientos de caja canónicos (Remediación A) refrescan KPIs.
    assert '"CASH_Z_CUT_GENERATED"' in src
    assert '_reload_section(0)' in src
