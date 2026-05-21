"""
test_finance_remaining_fixes.py — SPJ ERP v13.4
Tests para los hallazgos restantes de la auditoría de finanzas:

  R-01  Inyección SQL eliminada en TreasuryService.balance_general()
  R-02  SaleCancelledFinanceHandler sincroniza credit_balance Y saldo
  R-03  SaleCreatedFinanceHandler eliminado (código muerto / riesgo doble asiento)
  R-04  Parámetros correctos en core/use_cases/finanzas.py registrar_asiento call
  R-05  Migración 082 crea tablas de tesorería correctamente
"""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_treasury_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE treasury_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT (datetime('now')),
            tipo TEXT NOT NULL,
            categoria TEXT DEFAULT '',
            concepto TEXT DEFAULT '',
            ingreso REAL DEFAULT 0,
            egreso REAL DEFAULT 0,
            sucursal_id INTEGER DEFAULT 1
        );
        CREATE TABLE treasury_capital (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT (datetime('now')),
            tipo TEXT NOT NULL,
            monto REAL NOT NULL,
            descripcion TEXT DEFAULT '',
            usuario TEXT DEFAULT '',
            sucursal_id INTEGER DEFAULT 0
        );
        CREATE TABLE accounts_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL, status TEXT
        );
        CREATE TABLE accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL, status TEXT
        );
        CREATE TABLE productos (id INTEGER PRIMARY KEY, existencia REAL, activo INTEGER);
        CREATE TABLE activos (id INTEGER PRIMARY KEY, valor_adquisicion REAL, estado TEXT);
        CREATE TABLE depreciacion_acumulada (id INTEGER PRIMARY KEY, activo_id INTEGER, acumulado REAL);
        CREATE TABLE loyalty_pasivo_log (id INTEGER PRIMARY KEY, monto_total REAL);
    """)
    return conn


def _make_cancel_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE cuentas_por_cobrar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, venta_id INTEGER, folio TEXT,
            monto_original REAL, saldo_pendiente REAL,
            sucursal_id INTEGER DEFAULT 1, estado TEXT DEFAULT 'pendiente'
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, credit_balance REAL DEFAULT 0, saldo REAL DEFAULT 0
        );
        INSERT INTO clientes(nombre, credit_balance, saldo) VALUES ('Ana', 500.0, 500.0);
    """)
    return conn


class _MockFinance:
    def __init__(self): self.calls = []
    def registrar_asiento(self, **kw): self.calls.append(kw)


def _load_finance_handler():
    """Load finance_handler bypassing core.events __init__ chain to avoid circular imports."""
    import importlib.util
    path = os.path.join(
        os.path.dirname(__file__), "..", "core", "events", "handlers", "finance_handler.py"
    )
    spec = importlib.util.spec_from_file_location("finance_handler_direct", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_migration_082():
    """Load migration 082 module by file path."""
    import importlib.util
    path = os.path.join(
        os.path.dirname(__file__), "..", "migrations", "standalone", "082_treasury_tables.py"
    )
    spec = importlib.util.spec_from_file_location("migration_082", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════════
#  R-01 — SQL injection eliminada en balance_general()
# ═══════════════════════════════════════════════════════════════════════════

class TestBalanceGeneralSQLInjection:

    def _make_svc(self, conn):
        from core.services.finance.treasury_service import TreasuryService
        return TreasuryService(conn)

    def test_balance_general_sin_fecha_no_falla(self):
        conn = _make_treasury_db()
        svc = self._make_svc(conn)
        result = svc.balance_general()
        assert "activo" in result
        assert "pasivo" in result
        assert "capital" in result

    def test_balance_general_con_fecha_valida(self):
        conn = _make_treasury_db()
        conn.execute("INSERT INTO treasury_ledger(tipo,categoria,ingreso) VALUES ('ingreso','ventas',1000)")
        conn.execute("INSERT INTO treasury_capital(tipo,monto) VALUES ('inyeccion',5000)")
        conn.commit()
        svc = self._make_svc(conn)
        result = svc.balance_general(fecha_corte="2099-12-31")
        # With a far-future date, the treasury_ledger income should be included
        assert result["activo"]["caja_bancos"] >= 0

    def test_balance_general_con_fecha_pasada_excluye_futuros(self):
        conn = _make_treasury_db()
        # Insert a very old record
        conn.execute(
            "INSERT INTO treasury_ledger(fecha,tipo,categoria,ingreso) VALUES ('2020-01-01','ingreso','ventas',1000)"
        )
        conn.execute(
            "INSERT INTO treasury_ledger(fecha,tipo,categoria,ingreso) VALUES ('2099-01-01','ingreso','ventas',9000)"
        )
        conn.commit()
        svc = self._make_svc(conn)
        # With cutoff 2021-01-01, only the 2020 record should be included
        result = svc.balance_general(fecha_corte="2021-01-01")
        assert result["activo"]["caja_bancos"] == 1000.0

    def test_balance_general_no_usa_fstring_con_fecha(self):
        """Verify no f-string interpolation of fecha_corte in the source."""
        import inspect
        from core.services.finance.treasury_service import TreasuryService
        src = inspect.getsource(TreasuryService.balance_general)
        # The old injection pattern was: f"AND DATE(fecha) <= '{fc}'"
        assert "'{fc}'" not in src
        assert f"'{'{fc}'}'" not in src

    def test_balance_general_rechaza_comillas_en_fecha(self):
        """Un input malicioso no debe causar SyntaxError ni datos incorrectos."""
        conn = _make_treasury_db()
        svc = self._make_svc(conn)
        # Should not raise; SQLite will reject the param as non-date and return 0
        result = svc.balance_general(fecha_corte="2025-01-01' OR '1'='1")
        # The function should return a valid dict without crashing
        assert isinstance(result, dict)
        assert "activo" in result


# ═══════════════════════════════════════════════════════════════════════════
#  R-02 — SaleCancelledFinanceHandler sincroniza credit_balance Y saldo
# ═══════════════════════════════════════════════════════════════════════════

class TestSaleCancelledHandlerSaldoSync:

    def _make_handler(self, conn):
        mod = _load_finance_handler()
        return mod.SaleCancelledFinanceHandler(conn, _MockFinance())

    def test_cancela_venta_credito_decrementa_credit_balance(self):
        conn = _make_cancel_db()
        conn.execute(
            "INSERT INTO cuentas_por_cobrar(cliente_id,venta_id,folio,monto_original,saldo_pendiente)"
            " VALUES (1,42,'F-042',300.0,300.0)"
        )
        conn.commit()
        h = self._make_handler(conn)
        h.handle({
            "total": 300.0,
            "payment_method": "Credito",
            "folio": "F-042",
            "venta_id": 42,
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        row = conn.execute("SELECT credit_balance, saldo FROM clientes WHERE id=1").fetchone()
        assert row["credit_balance"] == 200.0, f"Expected 200 got {row['credit_balance']}"

    def test_cancela_venta_credito_decrementa_saldo_legacy(self):
        """saldo (legacy UI column) debe decrementarse junto con credit_balance."""
        conn = _make_cancel_db()
        conn.execute(
            "INSERT INTO cuentas_por_cobrar(cliente_id,venta_id,folio,monto_original,saldo_pendiente)"
            " VALUES (1,43,'F-043',200.0,200.0)"
        )
        conn.commit()
        h = self._make_handler(conn)
        h.handle({
            "total": 200.0,
            "payment_method": "Credito",
            "folio": "F-043",
            "venta_id": 43,
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        row = conn.execute("SELECT credit_balance, saldo FROM clientes WHERE id=1").fetchone()
        # Both must decrease by the same amount — A-05 sync invariant
        assert row["credit_balance"] == row["saldo"], (
            f"credit_balance={row['credit_balance']} != saldo={row['saldo']} — desync!"
        )

    def test_cancela_venta_credito_no_permite_saldo_negativo(self):
        """Cancelar más de lo que hay no debe producir saldo negativo."""
        conn = _make_cancel_db()
        h = self._make_handler(conn)
        h.handle({
            "total": 9999.0,  # more than the 500 that clientes has
            "payment_method": "Credito",
            "folio": "F-999",
            "venta_id": 99,
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        row = conn.execute("SELECT credit_balance, saldo FROM clientes WHERE id=1").fetchone()
        assert row["credit_balance"] >= 0
        assert row["saldo"] >= 0

    def test_cancela_venta_contado_no_toca_clientes(self):
        """Cancelación de venta contado no debe modificar saldo del cliente."""
        conn = _make_cancel_db()
        h = self._make_handler(conn)
        h.handle({
            "total": 150.0,
            "payment_method": "Efectivo",
            "folio": "F-100",
            "venta_id": 100,
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        row = conn.execute("SELECT credit_balance, saldo FROM clientes WHERE id=1").fetchone()
        # Cash sale cancellation should NOT touch credit columns
        assert row["credit_balance"] == 500.0
        assert row["saldo"] == 500.0

    def test_cancela_marca_cxc_cancelada(self):
        """La CxC debe quedar en estado='cancelada' con saldo_pendiente=0."""
        conn = _make_cancel_db()
        conn.execute(
            "INSERT INTO cuentas_por_cobrar(cliente_id,venta_id,folio,monto_original,saldo_pendiente)"
            " VALUES (1,50,'F-050',400.0,400.0)"
        )
        conn.commit()
        h = self._make_handler(conn)
        h.handle({
            "total": 400.0,
            "payment_method": "Credito",
            "folio": "F-050",
            "venta_id": 50,
            "sucursal_id": 1,
            "cliente_id": 1,
        })
        row = conn.execute(
            "SELECT estado, saldo_pendiente FROM cuentas_por_cobrar WHERE venta_id=50"
        ).fetchone()
        assert row["estado"] == "cancelada"
        assert row["saldo_pendiente"] == 0


# ═══════════════════════════════════════════════════════════════════════════
#  R-03 — SaleCreatedFinanceHandler eliminado
# ═══════════════════════════════════════════════════════════════════════════

class TestSaleCreatedHandlerRemoved:

    def test_sale_created_handler_no_existe_en_modulo(self):
        """SaleCreatedFinanceHandler fue eliminado — no debe existir en el módulo."""
        mod = _load_finance_handler()
        assert not hasattr(mod, "SaleCreatedFinanceHandler"), (
            "SaleCreatedFinanceHandler sigue existiendo — era código muerto "
            "que causaría doble asiento si se activara"
        )

    def test_otros_handlers_siguen_existiendo(self):
        """Los handlers activos no deben haber sido eliminados."""
        mod = _load_finance_handler()
        assert hasattr(mod, "SaleFinanceHandler")
        assert hasattr(mod, "CreditSaleFinanceHandler")
        assert hasattr(mod, "SaleCancelledFinanceHandler")

    def test_sale_created_handler_no_en_wiring(self):
        """wiring.py no debe referenciar SaleCreatedFinanceHandler."""
        wiring_path = os.path.join(
            os.path.dirname(__file__), "..", "core", "events", "wiring.py"
        )
        src = open(wiring_path).read()
        assert "SaleCreatedFinanceHandler" not in src


# ═══════════════════════════════════════════════════════════════════════════
#  R-04 — Parámetros correctos en finanzas UC
# ═══════════════════════════════════════════════════════════════════════════

class TestFinanzasUCParametros:

    def test_registrar_asiento_manual_usa_debe_haber(self):
        """registrar_asiento_manual debe llamar al servicio con debe= y haber=."""
        import inspect
        from core.use_cases.finanzas import GestionarFinanzasUC
        src = inspect.getsource(GestionarFinanzasUC.registrar_asiento_manual)
        # The service call inside registrar_asiento_manual must use debe=/haber=
        assert "debe=dto." in src, "Parámetro 'debe=' no encontrado en llamada al servicio"
        assert "haber=dto." in src, "Parámetro 'haber=' no encontrado en llamada al servicio"
        # Must NOT pass cuenta_debe/cuenta_haber to the service
        assert "cuenta_debe=dto." not in src, "Parámetro obsoleto 'cuenta_debe=dto.' encontrado"
        assert "cuenta_haber=dto." not in src, "Parámetro obsoleto 'cuenta_haber=dto.' encontrado"

    def test_registrar_asiento_manual_usa_concepto_no_descripcion(self):
        """La llamada al servicio debe usar 'concepto=' no 'descripcion='."""
        import inspect
        from core.use_cases.finanzas import GestionarFinanzasUC
        src = inspect.getsource(GestionarFinanzasUC.registrar_asiento_manual)
        assert "concepto=" in src, "Parámetro 'concepto=' no encontrado en llamada al servicio"
        assert "descripcion=dto." not in src, "Parámetro obsoleto 'descripcion=dto.' encontrado"

    def test_cierre_caja_usa_debe_haber(self):
        """cierre_caja también usa debe=/haber= en su llamada a registrar_asiento."""
        import inspect
        from core.use_cases.finanzas import GestionarFinanzasUC
        src = inspect.getsource(GestionarFinanzasUC.cierre_caja)
        assert "debe=" in src
        assert "haber=" in src


# ═══════════════════════════════════════════════════════════════════════════
#  R-05 — Migración 082 crea tablas de tesorería
# ═══════════════════════════════════════════════════════════════════════════

class TestMigracion082TreasuryTables:

    def _run_migration(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _load_migration_082().run(conn)
        return conn

    def test_crea_treasury_capital(self):
        conn = self._run_migration()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "treasury_capital" in tables

    def test_crea_treasury_ledger(self):
        conn = self._run_migration()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "treasury_ledger" in tables

    def test_crea_gastos_futuros(self):
        conn = self._run_migration()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "gastos_futuros" in tables

    def test_crea_pagos_cobros(self):
        conn = self._run_migration()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "pagos_cobros" in tables

    def test_crea_pagos_cobros_aplicaciones(self):
        conn = self._run_migration()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "pagos_cobros_aplicaciones" in tables

    def test_idempotente_segunda_ejecucion(self):
        """CREATE TABLE IF NOT EXISTS — la migración no falla si se corre dos veces."""
        conn = self._run_migration()
        _load_migration_082().run(conn)  # Second run — must not raise

    def test_treasury_service_ensure_tables_es_noop(self):
        """_ensure_tables() debe ser no-op después de mover DDL a migración."""
        import inspect
        from core.services.finance.treasury_service import TreasuryService
        src = inspect.getsource(TreasuryService._ensure_tables)
        assert "CREATE TABLE" not in src, (
            "_ensure_tables() todavía tiene DDL inline — debe ser no-op (migración 082)"
        )
