"""
test_finance_audit_fixes.py — SPJ ERP v13.4
Tests de seguridad para los hallazgos del FINANZAS_AUDIT_FIX_PLAN.

Cubre:
  F-01  pagar_nomina respeta metodo_pago
  F-04  FinancialDashboardService.crear_cliente valida nombre vacío
  F-05  FinancialDashboardService.listar_clientes / get_credit_info
  F-06  ThirdPartyService.check_duplicate_proveedor (lógica de UI extraída)
  A-07  No doble CxP al llamar crear_cxp dos veces con mismo concepto distinto
  A-08  No doble CxC por la ruta handler (CreditSaleFinanceHandler)
  A-09  FinanceService.registrar_asiento mantiene compatibilidad legacy
"""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ──────────────────────────────────────────────────────────────────

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
        CREATE TABLE nomina_pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER,
            periodo_inicio TEXT,
            periodo_fin TEXT,
            salario_base REAL,
            bonos REAL,
            deducciones REAL,
            total REAL,
            metodo_pago TEXT,
            estado TEXT,
            usuario TEXT,
            notas TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            telefono TEXT,
            email TEXT,
            activo INTEGER DEFAULT 1,
            sucursal_id INTEGER DEFAULT 1,
            fecha_registro TEXT,
            saldo REAL DEFAULT 0,
            limite_credito REAL DEFAULT 1000,
            credit_balance REAL DEFAULT 0
        );
        INSERT INTO clientes(nombre, limite_credito) VALUES ('Cliente A', 500.0);
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
        CREATE TABLE cuentas_por_cobrar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER, venta_id INTEGER,
            folio TEXT, monto_original REAL,
            saldo_pendiente REAL, sucursal_id INTEGER,
            estado TEXT DEFAULT 'pendiente',
            UNIQUE(venta_id)
        );
        CREATE TABLE cuentas_por_pagar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER, concepto TEXT,
            monto_original REAL, saldo_pendiente REAL,
            estado TEXT DEFAULT 'pendiente'
        );
        CREATE TABLE cuentas_bancarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, saldo REAL DEFAULT 0, activa INTEGER DEFAULT 1
        );
        INSERT INTO cuentas_bancarias(nombre, saldo) VALUES ('Caja principal', 5000.0);
        CREATE TABLE proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT, rfc TEXT, telefono TEXT,
            email TEXT, contacto TEXT, categoria TEXT,
            direccion TEXT, condiciones_pago INTEGER DEFAULT 0,
            limite_credito REAL DEFAULT 0, banco TEXT, notas TEXT,
            activo INTEGER DEFAULT 1
        );
    """)
    return conn


def _make_finance_service(conn):
    from core.services.enterprise.finance_service import FinanceService
    return FinanceService(conn)


def _make_tps(conn):
    from core.services.finance.third_party_service import UnifiedThirdPartyService
    return UnifiedThirdPartyService(conn)


def _make_dash_svc(conn):
    from core.services.finance.financial_dashboard_service import FinancialDashboardService
    return FinancialDashboardService(db=conn, treasury_service=None)


# ═══════════════════════════════════════════════════════════════════════════
#  F-01: pagar_nomina respeta metodo_pago
# ═══════════════════════════════════════════════════════════════════════════

class TestPagarNominaMetodoPago:
    def test_metodo_pago_transferencia(self):
        """F-01: metodo_pago='transferencia' debe guardarse, no 'efectivo'."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        np_id = svc.pagar_nomina(
            empleado_id=1,
            periodo_inicio="2026-05-01",
            periodo_fin="2026-05-15",
            salario_base=2000.0,
            metodo_pago="transferencia",
            usuario="rh_test",
        )
        row = conn.execute(
            "SELECT metodo_pago FROM nomina_pagos WHERE id=?", (np_id,)
        ).fetchone()
        assert row is not None
        assert row["metodo_pago"] == "transferencia", (
            f"Se esperaba 'transferencia', se obtuvo '{row['metodo_pago']}'"
        )

    def test_metodo_pago_cheque(self):
        """F-01: metodo_pago='cheque' debe persistirse correctamente."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        np_id = svc.pagar_nomina(
            empleado_id=2,
            periodo_inicio="2026-05-01",
            periodo_fin="2026-05-15",
            salario_base=1500.0,
            metodo_pago="cheque",
            usuario="admin",
        )
        row = conn.execute(
            "SELECT metodo_pago FROM nomina_pagos WHERE id=?", (np_id,)
        ).fetchone()
        assert row["metodo_pago"] == "cheque"

    def test_metodo_pago_efectivo_default(self):
        """F-01: metodo_pago por defecto es 'efectivo' (parámetro default)."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        np_id = svc.pagar_nomina(
            empleado_id=3,
            periodo_inicio="2026-05-01",
            periodo_fin="2026-05-15",
            salario_base=1000.0,
            usuario="rh",
        )
        row = conn.execute(
            "SELECT metodo_pago FROM nomina_pagos WHERE id=?", (np_id,)
        ).fetchone()
        assert row["metodo_pago"] == "efectivo"

    def test_asiento_generado_independiente_de_metodo(self):
        """F-01: el asiento contable se genera sin importar el método de pago."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        np_id = svc.pagar_nomina(
            empleado_id=4,
            periodo_inicio="2026-05-01",
            periodo_fin="2026-05-15",
            salario_base=3000.0,
            metodo_pago="deposito",
            usuario="test",
        )
        row = conn.execute(
            "SELECT evento, cuenta_debe, cuenta_haber FROM financial_event_log "
            "WHERE referencia_id=?", (np_id,)
        ).fetchone()
        assert row is not None
        assert row["evento"] == "NOMINA_PAGADA"
        assert row["cuenta_debe"] == "gasto_nomina"
        assert row["cuenta_haber"] == "caja_bancos"


# ═══════════════════════════════════════════════════════════════════════════
#  FinancialDashboardService — get_quick_kpis, listar_clientes, crear_cliente
# ═══════════════════════════════════════════════════════════════════════════

class TestFinancialDashboardService:
    def test_get_quick_kpis_devuelve_dict(self):
        """F-02: get_quick_kpis() retorna dict con claves esperadas."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        data = svc.get_quick_kpis()
        assert "cxc_pendiente"   in data
        assert "cxp_pendiente"   in data
        assert "saldo_tesoreria" in data
        assert "flujo_mes"       in data

    def test_saldo_tesoreria_suma_cuentas_bancarias(self):
        """F-02: saldo_tesoreria refleja cuentas_bancarias activas."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        data = svc.get_quick_kpis()
        assert data["saldo_tesoreria"] == 5000.0

    def test_get_quick_kpis_graceful_sin_tablas(self):
        """F-02: si faltan tablas, retorna ceros sin excepción."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from core.services.finance.financial_dashboard_service import FinancialDashboardService
        svc = FinancialDashboardService(db=conn)
        data = svc.get_quick_kpis()
        assert data["cxc_pendiente"]   == 0.0
        assert data["cxp_pendiente"]   == 0.0
        assert data["saldo_tesoreria"] == 0.0

    def test_get_quick_kpis_sin_db(self):
        """F-02: si db=None, retorna ceros sin excepción."""
        from core.services.finance.financial_dashboard_service import FinancialDashboardService
        svc = FinancialDashboardService(db=None)
        data = svc.get_quick_kpis()
        assert all(v == 0.0 for v in data.values())

    def test_get_credit_info_retorna_datos_cliente(self):
        """F-03: get_credit_info devuelve saldo, límite y nombre."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        info = svc.get_credit_info(1)
        assert info["limite_credito"] == 500.0
        assert info["nombre"] == "Cliente A"
        assert info["saldo_actual"] == 0.0

    def test_get_credit_info_cliente_inexistente(self):
        """F-03: cliente inexistente retorna valores vacíos sin excepción."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        info = svc.get_credit_info(9999)
        assert info["limite_credito"] == 0.0
        assert info["nombre"] == ""

    def test_listar_clientes_retorna_lista(self):
        """F-05: listar_clientes retorna lista de dicts con id y nombre."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        clientes = svc.listar_clientes()
        assert isinstance(clientes, list)
        assert len(clientes) >= 1
        assert "id" in clientes[0]
        assert "nombre" in clientes[0]

    def test_listar_clientes_sin_db(self):
        """F-05: sin db retorna lista vacía."""
        from core.services.finance.financial_dashboard_service import FinancialDashboardService
        svc = FinancialDashboardService(db=None)
        assert svc.listar_clientes() == []

    def test_crear_cliente_inserta_registro(self):
        """F-04: crear_cliente inserta en la tabla clientes y retorna ID."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        nuevo_id = svc.crear_cliente("Nuevo Cliente Test", telefono="5512345678")
        assert nuevo_id > 0
        row = conn.execute("SELECT nombre FROM clientes WHERE id=?", (nuevo_id,)).fetchone()
        assert row is not None
        assert row["nombre"] == "Nuevo Cliente Test"

    def test_crear_cliente_nombre_vacio_lanza_error(self):
        """F-04: nombre vacío debe lanzar ValueError."""
        conn = _make_db()
        svc  = _make_dash_svc(conn)
        try:
            svc.crear_cliente("")
            assert False, "Debía lanzar ValueError"
        except ValueError as exc:
            assert "nombre" in str(exc).lower() or "obligatorio" in str(exc).lower()


# ═══════════════════════════════════════════════════════════════════════════
#  F-06: check_duplicate_proveedor (lógica extraída de UI)
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckDuplicateProveedor:
    def _seed_proveedor(self, conn, nombre, rfc="", telefono=""):
        conn.execute(
            "INSERT INTO proveedores(nombre, rfc, telefono, activo) VALUES (?,?,?,1)",
            (nombre, rfc, telefono)
        )
        conn.commit()

    def test_sin_duplicado_retorna_none(self):
        """F-06: proveedor nuevo sin coincidencias retorna None."""
        conn = _make_db()
        tps  = _make_tps(conn)
        result = tps.check_duplicate_proveedor("Nuevo Proveedor Único")
        assert result is None

    def test_duplicado_por_nombre(self):
        """F-06: nombre normalizado igual → retorna motivo de duplicado."""
        conn = _make_db()
        self._seed_proveedor(conn, "Proveedor Alfa")
        tps = _make_tps(conn)
        motivo = tps.check_duplicate_proveedor("proveedor alfa")
        assert motivo is not None
        assert "nombre" in motivo.lower() or "proveedor alfa" in motivo.lower()

    def test_duplicado_por_rfc(self):
        """F-06: RFC igual (normalizado) → retorna motivo."""
        conn = _make_db()
        self._seed_proveedor(conn, "Otro Proveedor", rfc="AAA010101AAA")
        tps = _make_tps(conn)
        motivo = tps.check_duplicate_proveedor("Nuevo Proveedor", rfc="aaa010101aaa")
        assert motivo is not None
        assert "rfc" in motivo.lower() or "AAA010101AAA" in motivo

    def test_exclude_id_en_edicion(self):
        """F-06: exclude_id permite editar el mismo proveedor sin falso positivo."""
        conn = _make_db()
        self._seed_proveedor(conn, "Proveedor Beta")
        prov_id = conn.execute(
            "SELECT id FROM proveedores WHERE nombre='Proveedor Beta'"
        ).fetchone()[0]
        tps = _make_tps(conn)
        motivo = tps.check_duplicate_proveedor("Proveedor Beta", exclude_id=prov_id)
        assert motivo is None, "No debe reportar duplicado al editar el mismo proveedor"

    def test_sin_duplicado_retorna_none_cuando_db_vacia(self):
        """F-06: base de datos sin proveedores → siempre None."""
        conn = _make_db()
        tps = _make_tps(conn)
        result = tps.check_duplicate_proveedor("Cualquier Proveedor", rfc="AAA010101AAA")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
#  A-07: No doble CxP al crear dos CxP distintas
# ═══════════════════════════════════════════════════════════════════════════

class TestNoDobleCxP:
    def test_dos_cxp_distintas_no_se_mezclan(self):
        """A-07: dos crear_cxp con distinto concepto crean dos filas independientes."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        id1 = svc.crear_cxp(supplier_id=None, concepto="Compra A", amount=100.0, due_date="2026-06-01")
        id2 = svc.crear_cxp(supplier_id=None, concepto="Compra B", amount=200.0, due_date="2026-07-01")
        assert id1 != id2
        rows = conn.execute("SELECT id, concepto FROM accounts_payable ORDER BY id").fetchall()
        assert len(rows) == 2
        conceptos = {r["concepto"] for r in rows}
        assert "Compra A" in conceptos
        assert "Compra B" in conceptos

    def test_cxp_genera_exactamente_un_asiento(self):
        """A-07: crear_cxp genera exactamente un asiento en financial_event_log."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        ap_id = svc.crear_cxp(
            supplier_id=None, concepto="Compra única",
            amount=300.0, due_date="2026-12-31",
        )
        asientos = conn.execute(
            "SELECT id FROM financial_event_log WHERE referencia_id=? AND evento='CXP_CREADA'",
            (ap_id,)
        ).fetchall()
        assert len(asientos) == 1, f"Se esperaba 1 asiento, se encontraron {len(asientos)}"


# ═══════════════════════════════════════════════════════════════════════════
#  A-08: No doble CxC por handler (CreditSaleFinanceHandler)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoDobleCxC:
    def test_handler_usa_insert_or_ignore(self):
        """
        A-08: CreditSaleFinanceHandler usa INSERT OR IGNORE para evitar duplicados.
        Si se llama dos veces con el mismo venta_id, solo debe haber una CxC.
        """
        conn = _make_db()
        conn.row_factory = sqlite3.Row
        fs = _make_finance_service(conn)

        from core.events.handlers.finance_handler import CreditSaleFinanceHandler
        handler = CreditSaleFinanceHandler(db_conn=conn, finance_service=fs)

        payload = {
            "payment_method": "Credito",
            "total": 500.0,
            "cliente_id": 1,
            "sale_id": 42,
            "folio": "F-042",
            "branch_id": 1,
        }

        handler.handle(payload)
        handler.handle(payload)  # segunda llamada con mismo venta_id

        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM cuentas_por_cobrar WHERE venta_id=42"
        ).fetchone()
        assert rows["cnt"] == 1, (
            f"INSERT OR IGNORE debe evitar duplicado — se encontraron {rows['cnt']} filas"
        )

    def test_cxc_manual_genera_exactamente_un_asiento(self):
        """A-08: crear_cxc (manual) genera exactamente un asiento."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        ar_id = svc.crear_cxc(cliente_id=1, concepto="Servicio consultoria", amount=400.0)
        asientos = conn.execute(
            "SELECT id FROM financial_event_log WHERE referencia_id=? AND evento='CXC_CREADA'",
            (ar_id,)
        ).fetchall()
        assert len(asientos) == 1


# ═══════════════════════════════════════════════════════════════════════════
#  A-09: FinanceService.registrar_asiento mantiene compatibilidad legacy
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistrarAsientoCompatibilidadLegacy:
    def test_signature_debe_haber_monto_concepto(self):
        """A-09: la firma legacy (debe, haber, concepto, monto) sigue funcionando."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        row_id = svc.registrar_asiento(
            debe="caja",
            haber="ventas",
            concepto="Venta legacy",
            monto=100.0,
        )
        assert row_id > 0

    def test_retorna_cero_si_tabla_no_existe(self):
        """A-09: sin tabla financial_event_log retorna 0, no lanza excepción."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        from core.services.enterprise.finance_service import FinanceService
        svc = FinanceService(conn)
        result = svc.registrar_asiento("a", "b", "test", 10.0)
        assert result == 0

    def test_kwargs_adicionales_no_rompen_metodo(self):
        """A-09: parámetros opcionales (sucursal_id, evento, metadata) no rompen nada."""
        conn = _make_db()
        svc  = _make_finance_service(conn)
        row_id = svc.registrar_asiento(
            debe="gastos_operativos",
            haber="cuentas_por_pagar",
            concepto="Compra con metadata",
            monto=250.0,
            modulo="compras",
            sucursal_id=2,
            evento="CXP_CREADA",
            metadata={"proveedor": "Test"},
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT sucursal_id, evento FROM financial_event_log WHERE id=?", (row_id,)
        ).fetchone()
        assert row["sucursal_id"] == 2
        assert row["evento"] == "CXP_CREADA"
