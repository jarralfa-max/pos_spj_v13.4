# tests/test_fase3_plan_cuentas.py
# Fase 3 — plan_cuentas SAT (migración 059) y depreciacion_acumulada (migración 060)
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import importlib.util


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_migration(filename):
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "..", "migrations", "standalone", filename)
    spec = importlib.util.spec_from_file_location("_mig", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — Migración 059: plan_cuentas
# ══════════════════════════════════════════════════════════════════════════════

class TestMigracion059PlanCuentas:

    def test_tabla_plan_cuentas_creada(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='plan_cuentas'"
        ).fetchone()
        assert row is not None, "La tabla plan_cuentas debe existir"

    def test_columnas_requeridas(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(plan_cuentas)").fetchall()}
        required = {"codigo_sat", "nombre", "tipo", "nivel", "padre_id",
                    "activo", "descripcion", "created_at"}
        assert required.issubset(cols), f"Columnas faltantes: {required - cols}"

    def test_codigo_sat_unico(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO plan_cuentas(codigo_sat, nombre, tipo) VALUES('1101','Dupe','activo')"
            )
            conn.commit()

    def test_tipos_validos_insertados(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        tipos = {r[0] for r in conn.execute(
            "SELECT DISTINCT tipo FROM plan_cuentas"
        ).fetchall()}
        expected = {"activo", "pasivo", "capital", "ingreso", "costo", "gasto"}
        assert expected == tipos, f"Tipos presentes: {tipos}"

    def test_tipo_invalido_rechazado(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO plan_cuentas(codigo_sat, nombre, tipo) "
                "VALUES('9999','X','invalido')"
            )
            conn.commit()

    def test_catalogo_minimo_insertado(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        count = conn.execute("SELECT COUNT(*) FROM plan_cuentas").fetchone()[0]
        assert count >= 30, f"Se esperaban al menos 30 cuentas, hay {count}"

    def test_cuenta_caja_existe(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        row = conn.execute(
            "SELECT nombre FROM plan_cuentas WHERE codigo_sat='1101'"
        ).fetchone()
        assert row is not None
        assert "Caja" in row[0]

    def test_cuenta_depreciacion_acumulada_existe(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        row = conn.execute(
            "SELECT nombre FROM plan_cuentas WHERE codigo_sat='1302'"
        ).fetchone()
        assert row is not None
        assert "Depreciaci" in row[0]

    def test_cuenta_depreciacion_gasto_existe(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        row = conn.execute(
            "SELECT nombre FROM plan_cuentas WHERE codigo_sat='6105'"
        ).fetchone()
        assert row is not None

    def test_idempotente(self):
        conn = _mem_db()
        mod = _load_migration("059_plan_cuentas.py")
        mod.run(conn)
        mod.run(conn)   # segunda vez no debe lanzar
        conn.commit()

    def test_indice_codigo_existe(self):
        conn = _mem_db()
        _load_migration("059_plan_cuentas.py").run(conn)
        idx = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_pc_codigo'"
        ).fetchone()
        assert idx is not None


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — Migración 060: depreciacion_acumulada
# ══════════════════════════════════════════════════════════════════════════════

class TestMigracion060DepreciacionAcumulada:

    def test_tabla_creada(self):
        conn = _mem_db()
        _load_migration("060_depreciacion_acumulada.py").run(conn)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='depreciacion_acumulada'"
        ).fetchone()
        assert row is not None

    def test_columnas_requeridas(self):
        conn = _mem_db()
        _load_migration("060_depreciacion_acumulada.py").run(conn)
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(depreciacion_acumulada)"
        ).fetchall()}
        required = {"activo_id", "periodo", "monto_mes", "acumulado",
                    "cuenta_id", "created_at"}
        assert required.issubset(cols), f"Columnas faltantes: {required - cols}"

    def test_unique_activo_periodo(self):
        conn = _mem_db()
        _load_migration("060_depreciacion_acumulada.py").run(conn)
        conn.execute(
            "INSERT INTO depreciacion_acumulada(activo_id, periodo, monto_mes, acumulado) "
            "VALUES(1,'2026-01',100.0,100.0)"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO depreciacion_acumulada(activo_id, periodo, monto_mes, acumulado) "
                "VALUES(1,'2026-01',100.0,200.0)"
            )
            conn.commit()

    def test_insert_basico(self):
        conn = _mem_db()
        _load_migration("060_depreciacion_acumulada.py").run(conn)
        conn.execute(
            "INSERT INTO depreciacion_acumulada(activo_id, periodo, monto_mes, acumulado) "
            "VALUES(5,'2026-03',250.50,750.50)"
        )
        conn.commit()
        row = conn.execute(
            "SELECT monto_mes, acumulado FROM depreciacion_acumulada "
            "WHERE activo_id=5 AND periodo='2026-03'"
        ).fetchone()
        assert row is not None
        assert abs(row[0] - 250.50) < 0.01
        assert abs(row[1] - 750.50) < 0.01

    def test_idempotente(self):
        conn = _mem_db()
        mod = _load_migration("060_depreciacion_acumulada.py")
        mod.run(conn)
        mod.run(conn)
        conn.commit()
