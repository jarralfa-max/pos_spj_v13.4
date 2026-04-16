# tests/test_fase3_depreciacion.py
# Fase 3 — AssetService: accrual_depreciacion_mensual y capitalizar_mantenimiento
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _db_with_asset_tables():
    """DB en-memoria con tablas mínimas para AssetService."""
    conn = _mem_db()
    conn.executescript("""
        CREATE TABLE activos (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre               TEXT    NOT NULL,
            categoria            TEXT    DEFAULT '',
            numero_serie         TEXT    DEFAULT '',
            valor_adquisicion    REAL    NOT NULL DEFAULT 0,
            vida_util_anios      INTEGER DEFAULT 0,
            estado               TEXT    DEFAULT 'activo',
            fecha_adquisicion    TEXT    DEFAULT (date('now'))
        );
        CREATE TABLE mantenimientos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id   INTEGER NOT NULL,
            tipo        TEXT    DEFAULT 'preventivo',
            descripcion TEXT    DEFAULT '',
            fecha_prog  TEXT    DEFAULT (date('now')),
            estado      TEXT    DEFAULT 'pendiente',
            costo       REAL    DEFAULT 0,
            fecha_real  TEXT,
            realizado_por TEXT  DEFAULT ''
        );
        CREATE TABLE depreciacion_acumulada (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id   INTEGER NOT NULL,
            periodo     TEXT    NOT NULL,
            monto_mes   REAL    NOT NULL DEFAULT 0,
            acumulado   REAL    NOT NULL DEFAULT 0,
            cuenta_id   INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(activo_id, periodo)
        );
    """)
    conn.commit()
    return conn


def _make_asset_svc(conn, finance_service=None):
    from core.services.asset_service import AssetService
    svc = AssetService.__new__(AssetService)
    svc.db = conn
    svc.treasury_service = None
    svc.finance_service = finance_service
    return svc


def _insert_activo(conn, nombre="Freidora", valor=12000.0, vida=5, estado="activo"):
    cur = conn.execute(
        "INSERT INTO activos(nombre, valor_adquisicion, vida_util_anios, estado) "
        "VALUES(?,?,?,?)", (nombre, valor, vida, estado)
    )
    conn.commit()
    return cur.lastrowid


def _insert_mant(conn, activo_id, costo=500.0, estado="completado"):
    cur = conn.execute(
        "INSERT INTO mantenimientos(activo_id, tipo, descripcion, costo, estado) "
        "VALUES(?,?,?,?,?)",
        (activo_id, "correctivo", "Reparación mayor", costo, estado)
    )
    conn.commit()
    return cur.lastrowid


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — accrual_depreciacion_mensual
# ══════════════════════════════════════════════════════════════════════════════

class TestAccrualDepreciacion:

    def test_genera_registro_en_db(self):
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5)
        svc = _make_asset_svc(conn)
        res = svc.accrual_depreciacion_mensual("2026-04")
        assert res["ok"] is True
        row = conn.execute(
            "SELECT monto_mes FROM depreciacion_acumulada WHERE periodo='2026-04'"
        ).fetchone()
        assert row is not None

    def test_calculo_correcto(self):
        """12000 / (5 * 12) = 200.0 por mes"""
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5)
        svc = _make_asset_svc(conn)
        svc.accrual_depreciacion_mensual("2026-04")
        row = conn.execute(
            "SELECT monto_mes, acumulado FROM depreciacion_acumulada WHERE periodo='2026-04'"
        ).fetchone()
        assert abs(row["monto_mes"] - 200.0) < 0.01
        assert abs(row["acumulado"] - 200.0) < 0.01

    def test_acumulado_incremental(self):
        """Acumulado del mes 2 = 400.0"""
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5)
        svc = _make_asset_svc(conn)
        svc.accrual_depreciacion_mensual("2026-01")
        svc.accrual_depreciacion_mensual("2026-02")
        row = conn.execute(
            "SELECT acumulado FROM depreciacion_acumulada WHERE periodo='2026-02'"
        ).fetchone()
        assert abs(row["acumulado"] - 400.0) < 0.01

    def test_retorna_activos_procesados(self):
        conn = _db_with_asset_tables()
        _insert_activo(conn, nombre="Freidora", valor=12000.0, vida=5)
        _insert_activo(conn, nombre="Congelador", valor=24000.0, vida=10)
        svc = _make_asset_svc(conn)
        res = svc.accrual_depreciacion_mensual("2026-04")
        assert res["activos"] == 2

    def test_idempotente_mismo_periodo(self):
        """Llamar dos veces el mismo periodo no duplica el acumulado."""
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5)
        svc = _make_asset_svc(conn)
        svc.accrual_depreciacion_mensual("2026-04")
        svc.accrual_depreciacion_mensual("2026-04")   # segunda vez
        count = conn.execute(
            "SELECT COUNT(*) FROM depreciacion_acumulada WHERE periodo='2026-04'"
        ).fetchone()[0]
        assert count == 1

    def test_activo_baja_excluido(self):
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5, estado="baja")
        svc = _make_asset_svc(conn)
        res = svc.accrual_depreciacion_mensual("2026-04")
        assert res["activos"] == 0

    def test_sin_activos_devuelve_ok(self):
        conn = _db_with_asset_tables()
        svc = _make_asset_svc(conn)
        res = svc.accrual_depreciacion_mensual("2026-04")
        assert res["ok"] is True
        assert res["activos"] == 0

    def test_asiento_usa_debe_haber_correctos(self):
        """registrar_asiento() debe recibir debe='6105' y haber='1302' (Fase 3 fix)."""
        from unittest.mock import MagicMock
        conn = _db_with_asset_tables()
        _insert_activo(conn, valor=12000.0, vida=5)
        mock_fs = MagicMock()
        mock_fs.registrar_asiento.return_value = 1
        svc = _make_asset_svc(conn, finance_service=mock_fs)
        svc.accrual_depreciacion_mensual("2026-04")
        assert mock_fs.registrar_asiento.call_count == 1
        kwargs = mock_fs.registrar_asiento.call_args[1]
        assert kwargs.get("debe") == "6105", f"Esperado debe='6105', obtenido: {kwargs}"
        assert kwargs.get("haber") == "1302", f"Esperado haber='1302', obtenido: {kwargs}"
        assert kwargs.get("evento") == "DEPRECIACION_MENSUAL"


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — capitalizar_mantenimiento
# ══════════════════════════════════════════════════════════════════════════════

class TestCapitalizarMantenimiento:

    def test_incrementa_valor_activo(self):
        conn = _db_with_asset_tables()
        aid  = _insert_activo(conn, valor=10000.0, vida=5)
        mid  = _insert_mant(conn, activo_id=aid, costo=2000.0)
        svc  = _make_asset_svc(conn)
        res  = svc.capitalizar_mantenimiento(mid, aid)
        assert res["ok"] is True
        val = conn.execute(
            "SELECT valor_adquisicion FROM activos WHERE id=?", (aid,)
        ).fetchone()[0]
        assert abs(val - 12000.0) < 0.01

    def test_devuelve_monto_capitalizado(self):
        conn = _db_with_asset_tables()
        aid = _insert_activo(conn, valor=5000.0, vida=3)
        mid = _insert_mant(conn, activo_id=aid, costo=800.0)
        svc = _make_asset_svc(conn)
        res = svc.capitalizar_mantenimiento(mid, aid)
        assert abs(res["monto_capitalizado"] - 800.0) < 0.01

    def test_mant_no_completado_rechazado(self):
        conn = _db_with_asset_tables()
        aid = _insert_activo(conn)
        mid = _insert_mant(conn, activo_id=aid, costo=500.0, estado="pendiente")
        svc = _make_asset_svc(conn)
        res = svc.capitalizar_mantenimiento(mid, aid)
        assert res["ok"] is False

    def test_mant_sin_costo_rechazado(self):
        conn = _db_with_asset_tables()
        aid = _insert_activo(conn)
        mid = _insert_mant(conn, activo_id=aid, costo=0.0, estado="completado")
        svc = _make_asset_svc(conn)
        res = svc.capitalizar_mantenimiento(mid, aid)
        assert res["ok"] is False

    def test_activo_inexistente_rechazado(self):
        conn = _db_with_asset_tables()
        aid = _insert_activo(conn, valor=5000.0)
        mid = _insert_mant(conn, activo_id=aid, costo=500.0)
        svc = _make_asset_svc(conn)
        res = svc.capitalizar_mantenimiento(mid, activo_id=9999)
        assert res["ok"] is False

    def test_mant_marcado_capex(self):
        conn = _db_with_asset_tables()
        aid = _insert_activo(conn, valor=5000.0)
        mid = _insert_mant(conn, activo_id=aid, costo=300.0)
        svc = _make_asset_svc(conn)
        svc.capitalizar_mantenimiento(mid, aid)
        row = conn.execute(
            "SELECT tipo FROM mantenimientos WHERE id=?", (mid,)
        ).fetchone()
        assert row["tipo"] == "capex"
