"""
test_finance_service_methods.py — v13.4
Verifica los 6 métodos nuevos de FinanceService.
"""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_db():
    """DB en memoria con tablas mínimas para los tests de FinanceService."""
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

        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            precio REAL DEFAULT 0,
            precio_costo REAL DEFAULT 50.0
        );
        INSERT INTO productos (id, nombre, precio, precio_costo) VALUES (1, 'Pollo', 100.0, 50.0);
        INSERT INTO productos (id, nombre, precio, precio_costo) VALUES (2, 'Sin costo', 100.0, 0.0);

        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            limite_credito REAL DEFAULT 1000.0
        );
        INSERT INTO clientes (id, nombre, limite_credito) VALUES (1, 'Cliente A', 500.0);

        CREATE TABLE cuentas_por_cobrar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            saldo_pendiente REAL,
            estado TEXT DEFAULT 'pendiente'
        );

        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY,
            total REAL
        );
        INSERT INTO ventas VALUES (1, 200.0);

        CREATE TABLE venta_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            producto_id INTEGER,
            cantidad REAL
        );
        INSERT INTO venta_items (venta_id, producto_id, cantidad) VALUES (1, 1, 2.0);

        CREATE TABLE anticipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER,
            monto REAL,
            estado TEXT,
            usuario_id INTEGER,
            sucursal_id INTEGER
        );

        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            rfc TEXT,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            tipo TEXT DEFAULT 'general',
            condiciones_pago INTEGER DEFAULT 30,
            limite_credito REAL DEFAULT 0,
            banco TEXT,
            cuenta_bancaria TEXT,
            contacto TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            supplier_id INTEGER,
            concepto TEXT,
            amount REAL,
            balance REAL,
            due_date TEXT,
            status TEXT,
            tipo TEXT,
            referencia TEXT,
            ref_type TEXT,
            usuario TEXT,
            notas TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );

        CREATE TABLE ap_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ap_id INTEGER,
            monto REAL,
            metodo_pago TEXT,
            usuario TEXT,
            notas TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE accounts_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            cliente_id INTEGER,
            venta_id INTEGER,
            concepto TEXT,
            amount REAL,
            balance REAL,
            due_date TEXT,
            status TEXT,
            tipo TEXT,
            usuario TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );

        CREATE TABLE ar_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ar_id INTEGER,
            monto REAL,
            metodo_pago TEXT,
            usuario TEXT,
            notas TEXT,
            fecha TEXT DEFAULT (datetime('now'))
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
    """)
    return conn


def _make_service(conn):
    from core.services.enterprise.finance_service import FinanceService
    return FinanceService(conn)


class TestRegistrarAsiento:
    def test_inserts_row(self):
        conn = _make_db()
        svc = _make_service(conn)
        row_id = svc.registrar_asiento(
            debe="caja", haber="ventas",
            concepto="Venta de prueba", monto=100.0,
        )
        assert row_id > 0
        row = conn.execute(
            "SELECT * FROM financial_event_log WHERE id=?", (row_id,)
        ).fetchone()
        assert row["cuenta_debe"] == "caja"
        assert row["cuenta_haber"] == "ventas"
        assert float(row["monto"]) == 100.0

    def test_graceful_if_table_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        svc = _make_service(conn)
        result = svc.registrar_asiento("a", "b", "test", 10.0)
        assert result == 0  # no exception, returns 0


class TestObtenerLedger:
    def test_returns_entries_by_cuenta(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento("caja", "ventas", "entry1", 100.0)
        svc.registrar_asiento("inventario", "caja", "entry2", 50.0)
        entries = svc.obtener_ledger("caja")
        assert len(entries) == 2  # caja aparece como debe en entry1 y como haber en entry2

    def test_returns_empty_on_missing_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        svc = _make_service(conn)
        assert svc.obtener_ledger("caja") == []


class TestValidarMargen:
    def test_valid_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # producto 1: costo=50, precio=100 → margen=100% (bien por encima del 5% mínimo)
        assert svc.validar_margen(1, 100.0) is True

    def test_invalid_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # precio apenas por encima del costo → margen < 5%
        assert svc.validar_margen(1, 50.5) is False

    def test_zero_cost_product_is_permissive(self):
        conn = _make_db()
        svc = _make_service(conn)
        # producto 2: precio_costo=0 → permisivo
        assert svc.validar_margen(2, 1.0) is True

    def test_unknown_product_is_permissive(self):
        conn = _make_db()
        svc = _make_service(conn)
        assert svc.validar_margen(9999, 10.0) is True


class TestControlarCredito:
    def test_approved_within_limit(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_credito(1, 300.0)
        assert result["aprobado"] is True
        assert result["limite"] == 500.0

    def test_rejected_over_limit(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_credito(1, 600.0)
        assert result["aprobado"] is False


class TestControlarAnticipo:
    def test_registers_anticipo(self):
        conn = _make_db()
        svc = _make_service(conn)
        result = svc.controlar_anticipo(1, 50.0, usuario_id=1)
        assert result["registrado"] is True
        assert result["anticipo_id"] > 0
        # Verifica asiento contable generado
        ledger = svc.obtener_ledger("caja")
        assert len(ledger) >= 1


class TestCalcularMargenReal:
    def test_basic_margin(self):
        conn = _make_db()
        svc = _make_service(conn)
        # venta_id=1: total=200, items: 2 unidades de producto_id=1 (costo=50) → costo=100
        # margen = (200-100)/200 = 0.50
        margen = svc.calcular_margen_real(1)
        assert margen == 0.50

    def test_missing_venta_returns_minus_one(self):
        conn = _make_db()
        svc = _make_service(conn)
        assert svc.calcular_margen_real(9999) == -1.0


class TestSuppliersValidacionSat:
    def test_upsert_supplier_normaliza_rfc(self):
        conn = _make_db()
        svc = _make_service(conn)
        sid = svc.upsert_supplier({
            "nombre": "Proveedor Uno",
            "rfc": " aaa010101aaa ",
            "limite_credito": 1500.0,
            "condiciones_pago": 30,
        })
        row = conn.execute("SELECT rfc FROM suppliers WHERE id=?", (sid,)).fetchone()
        assert row["rfc"] == "AAA010101AAA"

    def test_upsert_supplier_rechaza_rfc_invalido(self):
        conn = _make_db()
        svc = _make_service(conn)
        try:
            svc.upsert_supplier({
                "nombre": "Proveedor Dos",
                "rfc": "RFC_INVALIDO",
            })
            assert False, "Se esperaba ValueError por RFC inválido"
        except ValueError as exc:
            assert "RFC" in str(exc)

    def test_upsert_supplier_rechaza_limite_negativo(self):
        conn = _make_db()
        svc = _make_service(conn)
        try:
            svc.upsert_supplier({
                "nombre": "Proveedor Tres",
                "rfc": "AAA010101AAA",
                "limite_credito": -1,
            })
            assert False, "Se esperaba ValueError por límite negativo"
        except ValueError as exc:
            assert "límite de crédito" in str(exc)


class TestAsientosAutomaticosFinanzas:
    def test_crear_cxp_genera_asiento(self):
        conn = _make_db()
        svc = _make_service(conn)
        ap_id = svc.crear_cxp(
            supplier_id=None,
            concepto="Compra de insumos",
            amount=500.0,
            due_date="2026-04-30",
        )
        assert ap_id > 0
        row = conn.execute(
            "SELECT evento, cuenta_debe, cuenta_haber FROM financial_event_log WHERE referencia_id=? ORDER BY id DESC LIMIT 1",
            (ap_id,),
        ).fetchone()
        assert row["evento"] == "CXP_CREADA"
        assert row["cuenta_debe"] == "gastos_operativos"
        assert row["cuenta_haber"] == "cuentas_por_pagar"

    def test_cobrar_cxc_genera_asiento(self):
        conn = _make_db()
        svc = _make_service(conn)
        ar_id = svc.crear_cxc(cliente_id=1, concepto="Venta a crédito", amount=300.0)
        r = svc.cobrar_cxc(ar_id=ar_id, monto=100.0, metodo_pago="transferencia")
        assert r["nuevo_status"] == "parcial"
        row = conn.execute(
            "SELECT evento, cuenta_debe, cuenta_haber FROM financial_event_log WHERE evento='CXC_COBRADA' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["cuenta_debe"] == "caja_bancos"
        assert row["cuenta_haber"] == "cuentas_por_cobrar"

    def test_pagar_nomina_genera_asiento(self):
        conn = _make_db()
        svc = _make_service(conn)
        np_id = svc.pagar_nomina(
            empleado_id=7,
            periodo_inicio="2026-04-01",
            periodo_fin="2026-04-15",
            salario_base=1000.0,
            bonos=50.0,
            deducciones=25.0,
            usuario="rh",
        )
        assert np_id > 0
        row = conn.execute(
            "SELECT evento, cuenta_debe, cuenta_haber, referencia_id FROM financial_event_log WHERE evento='NOMINA_PAGADA' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["cuenta_debe"] == "gasto_nomina"
        assert row["cuenta_haber"] == "caja_bancos"
        assert int(row["referencia_id"]) == int(np_id)


class TestGenerarPolizaPeriodo:
    def test_poliza_periodo_balanceada(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Ingreso contado",
            monto=100.0,
            modulo="ventas",
            evento="VENTA_COMPLETADA",
        )
        svc.registrar_asiento(
            debe="gasto_nomina",
            haber="caja_bancos",
            concepto="Nómina quincenal",
            monto=80.0,
            modulo="rrhh",
            evento="NOMINA_PAGADA",
        )

        pol = svc.generar_poliza_periodo("2000-01-01", "2100-12-31")
        assert pol["num_asientos"] >= 2
        assert pol["total_debe"] == pol["total_haber"]
        assert pol["balanceado"] is True
        assert len(pol["movimientos"]) >= 2

    def test_poliza_periodo_filtra_por_sucursal(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Sucursal 1",
            monto=50.0,
            modulo="ventas",
            sucursal_id=1,
            evento="VENTA_COMPLETADA",
        )
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Sucursal 2",
            monto=70.0,
            modulo="ventas",
            sucursal_id=2,
            evento="VENTA_COMPLETADA",
        )

        pol = svc.generar_poliza_periodo("2000-01-01", "2100-12-31", sucursal_id=2)
        assert pol["num_asientos"] >= 1
        assert all(m["sucursal_id"] == 2 for m in pol["movimientos"])


class TestExportarPolizaPeriodo:
    def test_exporta_json_valido(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Venta",
            monto=123.45,
            modulo="ventas",
            evento="VENTA_COMPLETADA",
        )
        payload = svc.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="json")
        assert "\"num_asientos\"" in payload
        assert "\"movimientos\"" in payload
        assert "VENTA_COMPLETADA" in payload

    def test_exporta_csv_con_headers(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Venta",
            monto=10.0,
            modulo="ventas",
            evento="VENTA_COMPLETADA",
        )
        csv_txt = svc.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="csv")
        assert "id,fecha,evento,modulo,referencia_id,debe,haber,monto,sucursal_id,metadata" in csv_txt
        assert "VENTA_COMPLETADA" in csv_txt

    def test_formato_invalido_lanza_error(self):
        conn = _make_db()
        svc = _make_service(conn)
        try:
            svc.exportar_poliza_periodo("2000-01-01", "2100-12-31", formato="xml")
            assert False, "Se esperaba ValueError por formato inválido"
        except ValueError as exc:
            assert "json" in str(exc).lower()

    def test_filtro_por_evento_y_cuenta(self):
        conn = _make_db()
        svc = _make_service(conn)
        svc.registrar_asiento(
            debe="caja_bancos",
            haber="ventas_contado",
            concepto="Venta",
            monto=100.0,
            modulo="ventas",
            evento="VENTA_COMPLETADA",
        )
        svc.registrar_asiento(
            debe="gasto_nomina",
            haber="caja_bancos",
            concepto="Nómina",
            monto=80.0,
            modulo="rrhh",
            evento="NOMINA_PAGADA",
        )

        pol = svc.generar_poliza_periodo(
            "2000-01-01", "2100-12-31",
            cuentas=["gasto_nomina"],
            eventos=["NOMINA_PAGADA"],
        )
        assert pol["num_asientos"] == 1
        assert pol["movimientos"][0]["evento"] == "NOMINA_PAGADA"
        assert pol["movimientos"][0]["debe"] == "gasto_nomina"
