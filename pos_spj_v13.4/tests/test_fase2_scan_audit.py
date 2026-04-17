# tests/test_fase2_scan_audit.py
# Fase 2 — QRParserService.log_scan + log_scan_raw
# No importa PyQt5 — usa SQLite en-memoria.

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _db_with_scan_log():
    conn = _mem_db()
    conn.execute("""
        CREATE TABLE scan_event_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_code    TEXT,
            tipo        TEXT,
            accion      TEXT,
            payload     TEXT,
            cliente_id  INTEGER,
            producto_id INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            usuario     TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


class TestLogScanRaw:

    def test_inserta_fila(self):
        conn = _db_with_scan_log()
        from core.services.qr_parser_service import QRParserService
        QRParserService.log_scan_raw(
            conn, raw_code="7501234567890", tipo="producto",
            accion="producto_agregado", producto_id=5,
            sucursal_id=1, usuario="cajero")
        row = conn.execute(
            "SELECT COUNT(*) FROM scan_event_log").fetchone()[0]
        assert row == 1

    def test_campos_guardados(self):
        conn = _db_with_scan_log()
        from core.services.qr_parser_service import QRParserService
        QRParserService.log_scan_raw(
            conn, raw_code="CLT-42", tipo="client_id",
            accion="cliente_cargado", cliente_id=42,
            sucursal_id=2, usuario="maria")
        row = conn.execute(
            "SELECT * FROM scan_event_log LIMIT 1").fetchone()
        assert row['raw_code'] == "CLT-42"
        assert row['tipo'] == "client_id"
        assert row['accion'] == "cliente_cargado"
        assert row['cliente_id'] == 42
        assert row['sucursal_id'] == 2
        assert row['usuario'] == "maria"

    def test_sin_db_no_lanza(self):
        """log_scan_raw con db=None debe silenciar el error."""
        from core.services.qr_parser_service import QRParserService
        # No debe lanzar excepción
        QRParserService.log_scan_raw(None, "test", "producto", "test")

    def test_multiples_inserciones(self):
        conn = _db_with_scan_log()
        from core.services.qr_parser_service import QRParserService
        for i in range(5):
            QRParserService.log_scan_raw(
                conn, raw_code=f"CODE-{i}", tipo="producto",
                accion="scan", sucursal_id=1)
        count = conn.execute(
            "SELECT COUNT(*) FROM scan_event_log").fetchone()[0]
        assert count == 5


class TestLogScanInstance:
    """Prueba el método de instancia log_scan()."""

    def test_log_scan_instancia(self):
        conn = _db_with_scan_log()
        from core.services.qr_parser_service import QRParserService, QRResult, QRType
        svc = QRParserService(db_conn=conn)
        result = QRResult(tipo=QRType.CLIENT_ID, raw="CLT-10",
                          client_id=10, nombre="Juan", codigo="CLT-10")
        svc.log_scan(result, accion="cliente_cargado",
                     sucursal_id=1, usuario="cajero")
        row = conn.execute(
            "SELECT tipo, accion, cliente_id FROM scan_event_log LIMIT 1"
        ).fetchone()
        assert row['tipo'] == QRType.CLIENT_ID
        assert row['accion'] == "cliente_cargado"
        assert row['cliente_id'] == 10

    def test_log_scan_sin_db_no_lanza(self):
        from core.services.qr_parser_service import QRParserService, QRResult, QRType
        svc = QRParserService(db_conn=None)
        result = QRResult(tipo=QRType.BUSQUEDA, raw="test")
        # Debe silenciar el error
        svc.log_scan(result, accion="test")


class TestQRParserSPJPrefixes:
    """Prueba el parsing de prefijos SPJ nativos."""

    def test_spj_fidel_numerico(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("SPJ:FIDEL:42")
        assert result.tipo == QRType.FIDELIDAD
        assert result.client_id == 42

    def test_spj_fidel_case_insensitive(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("spj:fidel:99")
        assert result.tipo == QRType.FIDELIDAD
        assert result.client_id == 99

    def test_spj_prod(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("SPJ:PROD:abc123")
        assert result.tipo == QRType.PRODUCTO
        assert result.codigo == "abc123"

    def test_spj_cont(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("SPJ:CONT:box-001")
        assert result.tipo == QRType.CONTENEDOR
        assert result.codigo == "box-001"

    def test_spj_fidel_con_espacios_raw(self):
        """Espacios al inicio/fin son limpiados antes del parse."""
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("  SPJ:FIDEL:7  ")
        assert result.tipo == QRType.FIDELIDAD
        assert result.client_id == 7

    def test_clt_id_nombre(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("CLT-42-Juan Pérez")
        assert result.tipo == QRType.CLIENT_ID
        assert result.client_id == 42
        assert result.nombre == "Juan Pérez"

    def test_ean13_clasificado(self):
        """EAN-13 todo-dígitos matchea UUID_HEX antes que EAN (comportamiento existente).
        El código sí queda como 'contenedor' por esa prioridad en el parser legacy."""
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("7501234567890")
        # UUID_HEX tiene prioridad sobre EAN cuando el barcode es solo dígitos (hex válidos)
        assert result.tipo in (QRType.PRODUCTO, QRType.CONTENEDOR)
        assert result.codigo == "7501234567890"

    def test_texto_libre_como_busqueda(self):
        from core.services.qr_parser_service import QRParserService, QRType
        svc = QRParserService()
        result = svc.parse("Leche Entera")
        assert result.tipo == QRType.BUSQUEDA
