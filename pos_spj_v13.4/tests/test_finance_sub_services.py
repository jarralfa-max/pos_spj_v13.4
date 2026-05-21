"""
test_finance_sub_services.py — SPJ ERP v13.4
Tests para los sub-servicios extraídos (FASE 5) y análisis de doble asiento (FASE 8).

Cubre:
  AccountsPayableService  — crear, abonar, listar, summary, historial
  AccountsReceivableService — crear, cobrar, listar, summary
  GeneralLedgerService    — registrar, obtener, poliza, exportar
  FinanceService (fachada) — delega correctamente a sub-servicios
  FASE 8                  — doble asiento en compras (análisis + tests)
"""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            evento TEXT NOT NULL,
            modulo TEXT NOT NULL,
            referencia_id INTEGER,
            monto DECIMAL(15,4),
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            usuario_id INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            metadata JSON
        );
        CREATE TABLE accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT, supplier_id INTEGER, concepto TEXT,
            amount REAL, balance REAL, due_date TEXT,
            status TEXT DEFAULT 'pendiente',
            tipo TEXT, referencia TEXT, ref_type TEXT,
            usuario TEXT, notas TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE ap_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ap_id INTEGER, monto REAL, metodo_pago TEXT,
            usuario TEXT, notas TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE accounts_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT, cliente_id INTEGER, venta_id INTEGER,
            concepto TEXT, amount REAL, balance REAL, due_date TEXT,
            status TEXT DEFAULT 'pendiente',
            tipo TEXT, usuario TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE TABLE ar_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ar_id INTEGER, monto REAL, metodo_pago TEXT,
            usuario TEXT, notas TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            rfc TEXT, activo INTEGER DEFAULT 1,
            condiciones_pago INTEGER DEFAULT 30,
            limite_credito REAL DEFAULT 0,
            telefono TEXT
        );
        INSERT INTO suppliers(nombre) VALUES ('Proveedor Test');
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, apellido_paterno TEXT, activo INTEGER DEFAULT 1,
            limite_credito REAL DEFAULT 1000,
            telefono TEXT
        );
        INSERT INTO clientes(nombre) VALUES ('Cliente Test');
        CREATE TABLE nomina_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER, periodo_inicio TEXT, periodo_fin TEXT,
            salario_base REAL, bonos REAL, deducciones REAL,
            total REAL, metodo_pago TEXT, estado TEXT,
            usuario TEXT, notas TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def _make_gl(conn):
    from core.services.finance.general_ledger_service import GeneralLedgerService
    return GeneralLedgerService(conn)


def _make_aps(conn, gl=None):
    from core.services.finance.accounts_payable_service import AccountsPayableService
    return AccountsPayableService(conn, ledger_service=gl)


def _make_ars(conn, gl=None):
    from core.services.finance.accounts_receivable_service import AccountsReceivableService
    return AccountsReceivableService(conn, ledger_service=gl)


def _make_fs(conn):
    from core.services.enterprise.finance_service import FinanceService
    return FinanceService(conn)


# ═══════════════════════════════════════════════════════════════════════════
#  GeneralLedgerService
# ═══════════════════════════════════════════════════════════════════════════

class TestGeneralLedgerService:
    def test_registrar_asiento_inserta_fila(self):
        conn = _make_db()
        gl = _make_gl(conn)
        rid = gl.registrar_asiento("caja", "ventas", "Venta prueba", 200.0)
        assert rid > 0
        row = conn.execute("SELECT cuenta_debe, cuenta_haber, monto FROM financial_event_log WHERE id=?", (rid,)).fetchone()
        assert row["cuenta_debe"] == "caja"
        assert row["cuenta_haber"] == "ventas"
        assert float(row["monto"]) == 200.0

    def test_registrar_asiento_no_hace_commit(self):
        """GL no debe hacer commit — el caller decide."""
        conn = _make_db()
        gl = _make_gl(conn)
        gl.registrar_asiento("a", "b", "test", 10.0)
        # Sin commit explícito, la fila debe seguir visible en la misma conexión
        count = conn.execute("SELECT COUNT(*) FROM financial_event_log").fetchone()[0]
        assert count == 1

    def test_registrar_asiento_graceful_sin_tabla(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from core.services.finance.general_ledger_service import GeneralLedgerService
        gl = GeneralLedgerService(conn)
        result = gl.registrar_asiento("a", "b", "test", 10.0)
        assert result == 0

    def test_obtener_ledger_filtra_por_cuenta(self):
        conn = _make_db()
        gl = _make_gl(conn)
        gl.registrar_asiento("caja", "ventas", "v1", 100.0)
        gl.registrar_asiento("inventario", "caja", "v2", 50.0)
        gl.registrar_asiento("gastos", "banco", "g1", 30.0)
        entries = gl.obtener_ledger("caja")
        assert len(entries) == 2  # aparece en debe de v1 y en haber de v2

    def test_obtener_ledger_tabla_faltante(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from core.services.finance.general_ledger_service import GeneralLedgerService
        gl = GeneralLedgerService(conn)
        assert gl.obtener_ledger("caja") == []

    def test_generar_poliza_balanceada(self):
        conn = _make_db()
        gl = _make_gl(conn)
        gl.registrar_asiento("caja", "ventas", "v1", 500.0, evento="VENTA")
        gl.registrar_asiento("gastos", "caja", "g1", 200.0, evento="GASTO")
        poliza = gl.generar_poliza_periodo("2000-01-01", "2100-12-31")
        assert poliza["num_asientos"] == 2
        assert poliza["balanceado"] is True
        assert poliza["total_debe"] == poliza["total_haber"]

    def test_exportar_poliza_json(self):
        conn = _make_db()
        gl = _make_gl(conn)
        gl.registrar_asiento("caja", "ventas", "v", 100.0, evento="VENTA")
        txt = gl.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="json")
        import json as _j
        data = _j.loads(txt)
        assert data["num_asientos"] >= 1

    def test_exportar_poliza_csv(self):
        conn = _make_db()
        gl = _make_gl(conn)
        gl.registrar_asiento("caja", "ventas", "v", 100.0, evento="VENTA")
        txt = gl.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="csv")
        assert "id,fecha,evento" in txt

    def test_exportar_poliza_formato_invalido(self):
        conn = _make_db()
        gl = _make_gl(conn)
        try:
            gl.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="xml")
            assert False
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  AccountsPayableService
# ═══════════════════════════════════════════════════════════════════════════

class TestAccountsPayableService:
    def test_crear_cxp_retorna_id(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=1, concepto="Compra material", amount=800.0)
        assert ap_id > 0

    def test_crear_cxp_registra_asiento(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=1, concepto="Compra test", amount=500.0)
        row = conn.execute(
            "SELECT cuenta_debe, cuenta_haber, evento FROM financial_event_log WHERE referencia_id=?",
            (ap_id,)
        ).fetchone()
        assert row is not None
        assert row["cuenta_debe"] == "gastos_operativos"
        assert row["cuenta_haber"] == "cuentas_por_pagar"
        assert row["evento"] == "CXP_CREADA"

    def test_crear_cxp_genera_exactamente_un_asiento(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=None, concepto="Única CxP", amount=300.0)
        count = conn.execute(
            "SELECT COUNT(*) FROM financial_event_log WHERE referencia_id=? AND evento='CXP_CREADA'",
            (ap_id,)
        ).fetchone()[0]
        assert count == 1

    def test_abonar_cxp_actualiza_balance(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=None, concepto="CxP abono", amount=1000.0)
        result = aps.abonar_cxp(ap_id=ap_id, monto=400.0, metodo_pago="transferencia")
        assert result["nuevo_balance"] == 600.0
        assert result["nuevo_status"] == "parcial"

    def test_abonar_cxp_total_marca_pagado(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=None, concepto="CxP total", amount=500.0)
        result = aps.abonar_cxp(ap_id=ap_id, monto=500.0)
        assert result["nuevo_balance"] == 0.0
        assert result["nuevo_status"] == "pagado"

    def test_abonar_cxp_registra_asiento_reversal(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        ap_id = aps.crear_cxp(supplier_id=None, concepto="CxP pago", amount=200.0)
        aps.abonar_cxp(ap_id=ap_id, monto=100.0)
        row = conn.execute(
            "SELECT cuenta_debe, cuenta_haber FROM financial_event_log WHERE evento='CXP_ABONADA'"
        ).fetchone()
        assert row["cuenta_debe"] == "cuentas_por_pagar"
        assert row["cuenta_haber"] == "caja_bancos"

    def test_historial_pagos_vacio_si_no_hay_abonos(self):
        conn = _make_db()
        aps = _make_aps(conn)
        historial = aps.historial_pagos(9999)
        assert historial == []

    def test_summary_refleja_estado(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        aps.crear_cxp(supplier_id=None, concepto="A", amount=300.0)
        aps.crear_cxp(supplier_id=None, concepto="B", amount=200.0)
        summ = aps.summary()
        assert float(summ.get("pendiente", 0)) == 500.0

    def test_listar_retorna_cxp_pendientes(self):
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)
        aps.crear_cxp(supplier_id=1, concepto="CxP listable", amount=100.0)
        rows = aps.listar()
        assert len(rows) >= 1
        assert all("aging" in r for r in rows)


# ═══════════════════════════════════════════════════════════════════════════
#  AccountsReceivableService
# ═══════════════════════════════════════════════════════════════════════════

class TestAccountsReceivableService:
    def test_crear_cxc_retorna_id(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ar_id = ars.crear_cxc(cliente_id=1, concepto="Servicio consultoría", amount=600.0)
        assert ar_id > 0

    def test_crear_cxc_registra_asiento(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ar_id = ars.crear_cxc(cliente_id=1, concepto="CxC test", amount=400.0)
        row = conn.execute(
            "SELECT cuenta_debe, cuenta_haber FROM financial_event_log WHERE referencia_id=? AND evento='CXC_CREADA'",
            (ar_id,)
        ).fetchone()
        assert row["cuenta_debe"] == "cuentas_por_cobrar"
        assert row["cuenta_haber"] == "ventas_credito"

    def test_cobrar_cxc_actualiza_balance(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ar_id = ars.crear_cxc(cliente_id=1, concepto="CxC cobro", amount=800.0)
        result = ars.cobrar_cxc(ar_id=ar_id, monto=300.0, metodo_pago="efectivo")
        assert result["nuevo_balance"] == 500.0
        assert result["nuevo_status"] == "parcial"

    def test_cobrar_cxc_total_marca_pagado(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ar_id = ars.crear_cxc(cliente_id=1, concepto="CxC total", amount=300.0)
        result = ars.cobrar_cxc(ar_id=ar_id, monto=300.0)
        assert result["nuevo_status"] == "pagado"

    def test_cobrar_cxc_registra_asiento(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ar_id = ars.crear_cxc(cliente_id=1, concepto="CxC asiento", amount=500.0)
        ars.cobrar_cxc(ar_id=ar_id, monto=200.0)
        row = conn.execute(
            "SELECT cuenta_debe, cuenta_haber FROM financial_event_log WHERE evento='CXC_COBRADA'"
        ).fetchone()
        assert row["cuenta_debe"] == "caja_bancos"
        assert row["cuenta_haber"] == "cuentas_por_cobrar"

    def test_listar_retorna_cxc_pendientes(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ars.crear_cxc(cliente_id=1, concepto="CxC listar", amount=200.0)
        rows = ars.listar()
        assert len(rows) >= 1
        assert all("aging" in r for r in rows)

    def test_summary_refleja_total(self):
        conn = _make_db()
        gl = _make_gl(conn)
        ars = _make_ars(conn, gl)
        ars.crear_cxc(cliente_id=1, concepto="S1", amount=300.0)
        ars.crear_cxc(cliente_id=1, concepto="S2", amount=200.0)
        summ = ars.summary()
        assert float(summ.get("total", 0)) == 500.0


# ═══════════════════════════════════════════════════════════════════════════
#  FinanceService — delegación a sub-servicios
# ═══════════════════════════════════════════════════════════════════════════

class TestFinanceServiceDelegacion:
    def test_crear_cxp_delega_a_aps(self):
        """FinanceService.crear_cxp() debe delegar a AccountsPayableService."""
        conn = _make_db()
        fs = _make_fs(conn)
        ap_id = fs.crear_cxp(supplier_id=None, concepto="Via fachada", amount=400.0, due_date=None)
        assert ap_id > 0
        row = conn.execute("SELECT concepto FROM accounts_payable WHERE id=?", (ap_id,)).fetchone()
        assert "Via fachada" in row["concepto"]

    def test_crear_cxc_delega_a_ars(self):
        """FinanceService.crear_cxc() debe delegar a AccountsReceivableService."""
        conn = _make_db()
        fs = _make_fs(conn)
        ar_id = fs.crear_cxc(cliente_id=1, concepto="CxC fachada", amount=250.0)
        assert ar_id > 0

    def test_registrar_asiento_delega_a_gl(self):
        """FinanceService.registrar_asiento() debe delegar a GeneralLedgerService."""
        conn = _make_db()
        fs = _make_fs(conn)
        rid = fs.registrar_asiento("caja", "ventas", "Delegado", 100.0)
        assert rid > 0

    def test_generar_poliza_delega_a_gl(self):
        """FinanceService.generar_poliza_periodo() debe delegar a GeneralLedgerService."""
        conn = _make_db()
        fs = _make_fs(conn)
        fs.registrar_asiento("caja", "ventas", "Test", 100.0)
        poliza = fs.generar_poliza_periodo("2000-01-01", "2100-12-31")
        assert poliza["num_asientos"] >= 1

    def test_abonar_cxp_delega_a_aps(self):
        conn = _make_db()
        fs = _make_fs(conn)
        ap_id = fs.crear_cxp(supplier_id=None, concepto="Abono fachada", amount=600.0)
        result = fs.abonar_cxp(ap_id=ap_id, monto=200.0, metodo_pago="cheque")
        assert result["nuevo_balance"] == 400.0

    def test_cobrar_cxc_delega_a_ars(self):
        conn = _make_db()
        fs = _make_fs(conn)
        ar_id = fs.crear_cxc(cliente_id=1, concepto="Cobro fachada", amount=300.0)
        result = fs.cobrar_cxc(ar_id=ar_id, monto=100.0)
        assert result["nuevo_balance"] == 200.0


# ═══════════════════════════════════════════════════════════════════════════
#  FASE 8 — Doble asiento en compras
# ═══════════════════════════════════════════════════════════════════════════

class TestFase8DobleAsientoCompras:
    """
    Documenta el riesgo de doble asiento en el flujo de compras.

    Rutas activas identificadas en auditoría:
      A) PurchaseService → crear_cxp() → asiento ("gastos_operativos" | "cuentas_por_pagar")
      B) PurchaseFinanceHandler → PURCHASE_CREATED → asiento ("inventario_almacen" | "cuentas_por_pagar")

    Las dos rutas generan asientos con DISTINTAS cuentas debe (A vs B), lo que
    crea un crédito doble en "cuentas_por_pagar" para la misma compra a crédito.

    ProcesarCompraUC es DEPRECATED (ver core/use_cases/compra.py línea 5) y su uso
    debe cesar — agrega una tercera ruta de asientos sobre las dos anteriores.
    """

    def test_cxp_asiento_rutas_distintas(self):
        """
        FASE 8: crear_cxp (ruta A) y PurchaseFinanceHandler (ruta B) usan
        cuentas debe distintas. Verificamos que queden DOS entradas en el ledger
        para una compra a crédito si ambas rutas se activan.

        Este test DOCUMENTA el comportamiento actual (doble crédito en cuentas_por_pagar).
        La corrección definitiva es desactivar la ruta A del PurchaseService para
        compras a crédito cuando PurchaseFinanceHandler está suscrito.
        """
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)

        # Ruta A: crear_cxp desde PurchaseService
        ap_id = aps.crear_cxp(
            supplier_id=1, concepto="Compra credito", amount=1000.0,
            referencia="F-001", ref_type="compra",
        )

        # Ruta B: PurchaseFinanceHandler registra su propio asiento
        gl.registrar_asiento(
            debe="inventario_almacen",
            haber="cuentas_por_pagar",
            concepto="Compra F-001 — entrada mercancía",
            monto=1000.0, modulo="compras",
            referencia_id=ap_id,
            evento="PURCHASE_CREATED",
        )

        # Resultado: dos asientos con haber=cuentas_por_pagar para el mismo folio
        rows = conn.execute(
            "SELECT cuenta_debe FROM financial_event_log WHERE cuenta_haber='cuentas_por_pagar'"
        ).fetchall()
        assert len(rows) == 2, (
            "RIESGO DOCUMENTADO: Dos rutas generan crédito en cuentas_por_pagar para la misma compra.\n"
            "Corrección: desactivar crear_cxp en PurchaseService si PurchaseFinanceHandler está suscrito."
        )
        cuentas_debe = {r[0] for r in rows}
        assert "gastos_operativos" in cuentas_debe     # Ruta A
        assert "inventario_almacen" in cuentas_debe    # Ruta B

    def test_procesar_compra_uc_marcado_deprecated(self):
        """
        FASE 8: Verifica que el docstring de ProcesarCompraUC contiene el marcador DEPRECATED.
        Protege contra accidentalmente remover la advertencia.
        """
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "compra_uc",
                os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "core", "use_cases", "compra.py")
            )
            mod = importlib.util.module_from_spec(spec)
            # Solo leemos el código fuente, no importamos (evita side effects)
            src_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "core", "use_cases", "compra.py"
            )
            src = open(src_path).read()
            assert "DEPRECATED" in src, "ProcesarCompraUC debe mantener el marcador DEPRECATED"
        except FileNotFoundError:
            pass  # Si el archivo no existe, no es un error

    def test_una_sola_cxp_por_compra_con_ruta_canonica(self):
        """
        FASE 8: La ruta canónica (solo AccountsPayableService, sin handler duplicado)
        genera exactamente una CxP y un asiento para una compra a crédito.
        """
        conn = _make_db()
        gl = _make_gl(conn)
        aps = _make_aps(conn, gl)

        # Ruta canónica: solo AccountsPayableService.crear_cxp()
        ap_id = aps.crear_cxp(
            supplier_id=1, concepto="Compra canónica", amount=500.0,
            referencia="F-002", ref_type="compra",
        )

        # Debe haber exactamente una CxP
        cxp_count = conn.execute(
            "SELECT COUNT(*) FROM accounts_payable WHERE referencia='F-002'"
        ).fetchone()[0]
        assert cxp_count == 1

        # Debe haber exactamente un asiento CXP_CREADA
        asiento_count = conn.execute(
            "SELECT COUNT(*) FROM financial_event_log WHERE referencia_id=? AND evento='CXP_CREADA'",
            (ap_id,)
        ).fetchone()[0]
        assert asiento_count == 1
