"""Remediación F — health_monitor delega su SQL a SystemHealthRepository.

Caracteriza las 4 lecturas de diagnóstico extraídas de
modulos/sistema/health_monitor.py. El contrato clave es que NUNCA lanzan: si el
esquema no tiene las columnas esperadas, degradan a 0 / [].
"""
import sqlite3

import pytest

from repositories.system_health_repository import SystemHealthRepository


def _repo(conn):
    return SystemHealthRepository(connection_factory=lambda: conn)


@pytest.fixture
def conn_compat():
    """Conexión con el esquema de diagnóstico esperado (logs/sync_eventos)."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE logs (nivel TEXT, modulo TEXT, mensaje TEXT, fecha TEXT)")
    c.execute("CREATE TABLE sync_eventos (enviado INTEGER)")
    c.execute("INSERT INTO logs VALUES ('ERROR','ventas','boom', datetime('now'))")
    c.execute("INSERT INTO logs VALUES ('CRITICAL','caja','kaput', datetime('now'))")
    c.execute("INSERT INTO logs VALUES ('INFO','x','ok', datetime('now'))")  # no cuenta
    c.execute("INSERT INTO sync_eventos VALUES (0)")
    c.execute("INSERT INTO sync_eventos VALUES (0)")
    c.execute("INSERT INTO sync_eventos VALUES (1)")  # enviado, no cuenta
    c.commit()
    return c


def test_ping_ok(conn_compat):
    assert _repo(conn_compat).ping() is True


def test_ping_falla_sin_conexion():
    def _boom():
        raise RuntimeError("sin conexión")
    assert SystemHealthRepository(connection_factory=_boom).ping() is False


def test_error_count_24h(conn_compat):
    assert _repo(conn_compat).error_count_24h() == 2   # ERROR + CRITICAL


def test_pending_sync_count(conn_compat):
    assert _repo(conn_compat).pending_sync_count() == 2  # dos con enviado=0


def test_recent_errors(conn_compat):
    rows = _repo(conn_compat).recent_errors(limit=10)
    niveles = {r["nivel"] for r in rows}
    assert niveles == {"ERROR", "CRITICAL"}   # INFO excluido


def test_degrada_a_cero_sin_columnas():
    """Esquema born-clean (logs sin nivel/mensaje) → 0 / [] sin excepción."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE logs (id TEXT, fecha TEXT, modulo TEXT)")  # sin nivel/mensaje
    c.commit()
    r = _repo(c)
    assert r.error_count_24h() == 0
    assert r.pending_sync_count() == 0     # tabla sync_eventos inexistente
    assert r.recent_errors() == []


def test_get_system_health_no_crashea(conn_compat):
    import modulos.sistema.health_monitor as hm
    # inyecta el repo con la conexión compatible
    orig = hm.SystemHealthRepository
    hm.SystemHealthRepository = lambda *a, **k: _repo(conn_compat)
    try:
        h = hm.get_system_health()
        assert h["db_ok"] is True
        assert h["error_count_24h"] == 2
        assert "status" in h
    finally:
        hm.SystemHealthRepository = orig
