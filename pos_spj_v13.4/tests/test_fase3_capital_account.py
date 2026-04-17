# tests/test_fase3_capital_account.py
# Fase 3 — CapitalAccount (wrapper treasury_capital)
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _db_with_treasury_capital():
    """DB en-memoria con tabla treasury_capital mínima."""
    conn = _mem_db()
    conn.executescript("""
        CREATE TABLE treasury_capital (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo       TEXT    NOT NULL DEFAULT 'inyeccion',
            monto      REAL    NOT NULL DEFAULT 0,
            concepto   TEXT    DEFAULT '',
            usuario    TEXT    DEFAULT 'sistema',
            created_at TEXT    DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


def _make_treasury_svc(conn):
    from core.services.treasury_service import TreasuryService
    svc = TreasuryService.__new__(TreasuryService)
    svc.db = conn
    svc._module_config = None
    return svc


def _make_capital_account(conn):
    from core.services.treasury_service import CapitalAccount
    tsvc = _make_treasury_svc(conn)
    return CapitalAccount(tsvc), tsvc


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — saldo_actual
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalAccountSaldo:

    def test_saldo_inicial_cero(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        assert ca.saldo_actual() == 0.0

    def test_saldo_tras_inyeccion(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(5000.0)
        assert ca.saldo_actual() == 5000.0

    def test_saldo_acumulado_multiples_inyecciones(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(3000.0)
        ca.inyectar(2000.0)
        assert ca.saldo_actual() == 5000.0

    def test_saldo_tras_retiro(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(10000.0)
        ca.retirar(4000.0)
        assert abs(ca.saldo_actual() - 6000.0) < 0.01

    def test_saldo_nunca_negativo(self):
        """Saldo debe ser >= 0 incluso si retiros > inyecciones en DB."""
        conn = _db_with_treasury_capital()
        conn.execute(
            "INSERT INTO treasury_capital(tipo, monto) VALUES('retiro', 999)"
        )
        conn.commit()
        ca, _ = _make_capital_account(conn)
        assert ca.saldo_actual() >= 0.0


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — inyectar
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalAccountInyectar:

    def test_inyectar_ok(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        res = ca.inyectar(1500.0, concepto="Aportación socios", usuario="gerente")
        assert res["ok"] is True
        assert res["tipo"] == "inyeccion"
        assert res["monto"] == 1500.0

    def test_inyectar_monto_cero_rechazado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        res = ca.inyectar(0)
        assert res["ok"] is False
        assert "error" in res

    def test_inyectar_monto_negativo_rechazado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        res = ca.inyectar(-100.0)
        assert res["ok"] is False

    def test_inyectar_persiste_en_db(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(2500.0, concepto="Prueba")
        row = conn.execute(
            "SELECT monto, tipo FROM treasury_capital WHERE tipo='inyeccion' LIMIT 1"
        ).fetchone()
        assert row is not None
        assert abs(row["monto"] - 2500.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — retirar
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalAccountRetirar:

    def test_retirar_ok(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(5000.0)
        res = ca.retirar(1000.0, concepto="Retiro dueño")
        assert res["ok"] is True
        assert res["tipo"] == "retiro"
        assert res["monto"] == 1000.0

    def test_retirar_sin_saldo_rechazado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        res = ca.retirar(100.0)
        assert res["ok"] is False
        assert "error" in res

    def test_retirar_exceso_rechazado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(500.0)
        res = ca.retirar(600.0)
        assert res["ok"] is False

    def test_retirar_monto_cero_rechazado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(1000.0)
        res = ca.retirar(0)
        assert res["ok"] is False

    def test_retirar_actualiza_saldo(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(8000.0)
        ca.retirar(3000.0)
        assert abs(ca.saldo_actual() - 5000.0) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — historial
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalAccountHistorial:

    def test_historial_retorna_lista(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        ca.inyectar(1000.0)
        ca.inyectar(2000.0)
        result = ca.historial()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_historial_vacio_retorna_lista_vacia(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        result = ca.historial()
        assert result == []

    def test_historial_limit_respetado(self):
        conn = _db_with_treasury_capital()
        ca, _ = _make_capital_account(conn)
        for i in range(5):
            ca.inyectar(100.0 * (i + 1))
        result = ca.historial(limit=3)
        assert len(result) == 3
