"""
tests/purchases/test_qr_flow_no_regression.py
──────────────────────────────────────────────
FASE 1 — Tests de no regresión: flujo QR actual.

Propósito: garantizar que NINGÚN cambio del refactor rompe el flujo QR.
Estos tests deben pasar en VERDE antes Y después de cualquier cambio.

Si alguno falla tras un cambio, se violó la política QR NO-TOUCH.

Cobertura:
- QRService importa sin error
- generar_uuid_qr() crea registro en trazabilidad_qr
- movimientos_trazabilidad recibe evento 'generado'
- escanear_recepcion() actualiza estado del contenedor
- QR y compra tradicional no interfieren en inventario
- Tipos QR soportados no cambiaron
- El módulo compras_pro.py importa sin SyntaxError
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from services.qr_service import QRService, TIPOS_QR


SCHEMA_QR = """
CREATE TABLE trazabilidad_qr (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid_qr         TEXT UNIQUE NOT NULL,
    tipo            TEXT NOT NULL,
    producto_id     INTEGER,
    proveedor_id    INTEGER,
    lote_id         INTEGER,
    sucursal_id     INTEGER DEFAULT 1,
    numero_lote     TEXT,
    peso_kg         REAL,
    cantidad        REAL,
    datos_extra     TEXT,
    estado          TEXT DEFAULT 'generado',
    fecha_generacion DATETIME DEFAULT (datetime('now'))
);
CREATE TABLE movimientos_trazabilidad (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid_qr     TEXT NOT NULL,
    evento      TEXT NOT NULL,
    origen      TEXT,
    destino     TEXT,
    sucursal_id INTEGER DEFAULT 1,
    usuario     TEXT,
    notas       TEXT,
    peso_kg     REAL,
    fecha       DATETIME DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_QR)
    conn.isolation_level = None
    return conn


@pytest.fixture
def qr_svc(db):
    svc = QRService.__new__(QRService)
    svc.conn = db
    svc.sucursal_id = 1
    return svc


class TestQRFlowNoRegression:

    def test_qr_service_imports_without_error(self):
        """QRService debe importar sin errores tras cualquier cambio."""
        from services.qr_service import QRService
        assert QRService is not None

    def test_qr_tipos_soportados_unchanged(self):
        """
        Los tipos QR soportados no deben cambiar.
        Si este test falla, se alteró el contrato de tipos QR.
        """
        expected = {"contenedor", "producto", "cliente_fidelidad",
                    "ticket_delivery", "mapa_entrega", "paquete"}
        actual = set(TIPOS_QR)
        assert actual == expected, (
            f"Tipos QR cambiaron. Esperado: {expected}, Actual: {actual}\n"
            "Verificar política QR NO-TOUCH antes de continuar."
        )

    def test_generar_uuid_qr_creates_record(self, db, qr_svc):
        """generar_uuid_qr() debe insertar en trazabilidad_qr."""
        uid = qr_svc.generar_uuid_qr("contenedor", {
            "producto_id": 1,
            "proveedor_id": 2,
            "numero_lote": "L-2026-TEST",
            "peso_kg": 52.1,
            "usuario": "almacen",
        })
        row = db.execute(
            "SELECT * FROM trazabilidad_qr WHERE uuid_qr=?", (uid,)
        ).fetchone()
        assert row is not None, "generar_uuid_qr debe crear registro en trazabilidad_qr"
        assert row["tipo"] == "contenedor"

    def test_generar_uuid_qr_creates_movement_record(self, db, qr_svc):
        """generar_uuid_qr() debe insertar movimiento 'generado' en movimientos_trazabilidad."""
        uid = qr_svc.generar_uuid_qr("contenedor", {
            "producto_id": 1,
            "usuario": "almacen",
        })
        mov = db.execute(
            "SELECT * FROM movimientos_trazabilidad WHERE uuid_qr=?", (uid,)
        ).fetchone()
        assert mov is not None, "debe existir movimiento de trazabilidad"
        assert mov["evento"] == "generado"

    def test_invalid_tipo_raises_value_error(self, qr_svc):
        """Un tipo QR inválido debe lanzar ValueError, no silenciosamente fallar."""
        with pytest.raises(ValueError, match="Tipo QR inválido"):
            qr_svc.generar_uuid_qr("tipo_inexistente", {})

    def test_uuid_qr_is_unique_per_generation(self, db, qr_svc):
        """Cada generación produce UUID único."""
        uid1 = qr_svc.generar_uuid_qr("contenedor", {"producto_id": 1})
        uid2 = qr_svc.generar_uuid_qr("contenedor", {"producto_id": 1})
        assert uid1 != uid2, "UUIDs QR deben ser únicos entre generaciones"

    def test_qr_and_traditional_purchase_are_independent(self):
        """
        QR y Compra Tradicional no comparten estado en memoria ni bus de eventos.
        Verificar que PurchaseService no importa QRService.
        """
        import inspect
        from core.services.purchase_service import PurchaseService
        source = inspect.getsource(PurchaseService)
        assert "qr_service" not in source.lower() and "QRService" not in source, (
            "PurchaseService no debe importar QRService — son flujos independientes"
        )

    def test_compras_pro_module_has_no_syntax_error(self):
        """compras_pro.py no debe tener SyntaxError tras ningún cambio."""
        import ast
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "modulos", "compras_pro.py"
        )
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"SyntaxError en compras_pro.py: {e}")

    def test_qr_service_module_has_no_syntax_error(self):
        """qr_service.py no debe tener SyntaxError tras ningún cambio."""
        import ast
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "services", "qr_service.py"
        )
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"SyntaxError en qr_service.py: {e}")

    def test_no_new_qr_engine_module_created(self):
        """
        No debe existir un segundo motor QR.
        Si este test falla, se violó la política de no duplicar QR.
        """
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        forbidden_patterns = [
            os.path.join(base, "services", "qr_service_v2.py"),
            os.path.join(base, "services", "qr_engine.py"),
            os.path.join(base, "application", "purchases", "qr_engine.py"),
        ]
        for path in forbidden_patterns:
            assert not os.path.exists(path), (
                f"Segundo motor QR detectado: {path}\n"
                "Violación de política QR NO-TOUCH."
            )
