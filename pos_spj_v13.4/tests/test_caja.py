# tests/test_caja.py
"""
Tests de regresión para el módulo de caja.
Cubre: turno, movimientos, corte Z, eventos, historial.
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest

# Asegurar que el path del proyecto esté disponible
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fixture: BD en memoria ─────────────────────────────────────────────────────

@pytest.fixture
def db():
    """Crea una BD SQLite en memoria con el esquema mínimo para pruebas de caja."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS turnos_caja (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id    INTEGER DEFAULT 1,
            usuario        TEXT,
            cajero         TEXT,
            fondo_inicial  REAL DEFAULT 0,
            total_ventas   REAL DEFAULT 0,
            total_efectivo REAL DEFAULT 0,
            retiros        REAL DEFAULT 0,
            estado         TEXT DEFAULT 'abierto',
            fecha_apertura DATETIME DEFAULT (datetime('now')),
            fecha_cierre   DATETIME,
            efectivo_esperado REAL DEFAULT 0,
            efectivo_contado  REAL DEFAULT 0,
            diferencia        REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS movimientos_caja (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            turno_id    INTEGER,
            sucursal_id INTEGER DEFAULT 1,
            tipo        TEXT,
            monto       REAL DEFAULT 0,
            concepto    TEXT,
            descripcion TEXT,
            usuario     TEXT,
            fecha       DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cierres_caja (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid                TEXT UNIQUE,
            tipo                TEXT DEFAULT 'Z',
            sucursal_id         INTEGER DEFAULT 1,
            usuario             TEXT,
            turno               TEXT,
            fecha_apertura      DATETIME,
            fecha_cierre        DATETIME DEFAULT (datetime('now')),
            total_ventas        REAL DEFAULT 0,
            num_ventas          INTEGER DEFAULT 0,
            total_efectivo      REAL DEFAULT 0,
            total_tarjeta       REAL DEFAULT 0,
            total_transferencia REAL DEFAULT 0,
            total_otros         REAL DEFAULT 0,
            total_anulaciones   REAL DEFAULT 0,
            num_anulaciones     INTEGER DEFAULT 0,
            efectivo_contado    REAL DEFAULT 0,
            fondo_inicial       REAL DEFAULT 0,
            diferencia          REAL DEFAULT 0,
            comentarios         TEXT,
            estado              TEXT DEFAULT 'cerrado'
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sucursal_id INTEGER DEFAULT 1,
            cajero      TEXT,
            usuario     TEXT,
            total       REAL DEFAULT 0,
            forma_pago  TEXT DEFAULT 'Efectivo',
            estado      TEXT DEFAULT 'completada',
            fecha       DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS financial_event_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            evento       TEXT,
            modulo       TEXT,
            referencia_id INTEGER,
            monto        REAL,
            cuenta_debe  TEXT,
            cuenta_haber TEXT,
            usuario_id   INTEGER,
            sucursal_id  INTEGER,
            metadata     TEXT,
            created_at   DATETIME DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


@pytest.fixture
def svc(db):
    """Instancia CajaApplicationService con BD en memoria."""
    from application.services.caja_application_service import CajaApplicationService
    return CajaApplicationService(db=db, finance_service=None, caja_repo=None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _insertar_venta(db, sucursal_id=1, cajero="test_cajero", total=100.0,
                    forma_pago="Efectivo", estado="completada"):
    db.execute(
        "INSERT INTO ventas (sucursal_id, cajero, usuario, total, forma_pago, estado, fecha) "
        "VALUES (?,?,?,?,?,?,datetime('now'))",
        (sucursal_id, cajero, cajero, total, forma_pago, estado)
    )
    db.commit()


# ── Tests: abrir turno ────────────────────────────────────────────────────────

def test_abrir_turno_exitoso(svc):
    turno_id = svc.abrir_turno(1, "cajero1", 500.0)
    assert turno_id > 0


def test_abrir_turno_retorna_id(svc):
    tid = svc.abrir_turno(1, "cajero_x", 200.0)
    assert isinstance(tid, int)


def test_no_permitir_doble_turno_abierto(svc):
    from application.services.caja_application_service import TurnoYaAbiertroError
    svc.abrir_turno(1, "cajero2", 300.0)
    with pytest.raises(TurnoYaAbiertroError):
        svc.abrir_turno(1, "cajero2", 100.0)


def test_dos_cajeros_diferentes_pueden_abrir(svc):
    """Cajeros distintos pueden tener turnos abiertos simultáneos."""
    svc.abrir_turno(1, "cajeroA", 100.0)
    # Cajero B en misma sucursal es independiente
    tid_b = svc.abrir_turno(1, "cajeroB", 200.0)
    assert tid_b > 0


def test_get_estado_turno_abierto(svc):
    svc.abrir_turno(1, "cajero3", 150.0)
    estado = svc.get_estado_turno(1, "cajero3")
    assert estado is not None
    assert float(estado['fondo_inicial']) == 150.0


def test_get_estado_turno_cerrado(svc):
    estado = svc.get_estado_turno(1, "cajero_sin_turno")
    assert estado is None


# ── Tests: registrar movimiento ───────────────────────────────────────────────

def test_registrar_ingreso(svc):
    tid = svc.abrir_turno(1, "cajero4", 100.0)
    svc.registrar_movimiento_manual(tid, 1, "cajero4", "INGRESO", 50.0, "Cambio extra")
    movs = svc.get_movimientos_turno(tid)
    assert any(m.get('tipo') == 'INGRESO' for m in movs)


def test_registrar_retiro(svc):
    tid = svc.abrir_turno(1, "cajero5", 300.0)
    svc.registrar_movimiento_manual(tid, 1, "cajero5", "RETIRO", 80.0, "Pago proveedor")
    movs = svc.get_movimientos_turno(tid)
    assert any(m.get('tipo') == 'RETIRO' for m in movs)


def test_movimiento_monto_invalido(svc):
    tid = svc.abrir_turno(1, "cajero6", 100.0)
    with pytest.raises(ValueError):
        svc.registrar_movimiento_manual(tid, 1, "cajero6", "INGRESO", 0.0, "Sin monto")


def test_movimiento_tipo_invalido(svc):
    tid = svc.abrir_turno(1, "cajero7", 100.0)
    with pytest.raises(ValueError):
        svc.registrar_movimiento_manual(tid, 1, "cajero7", "VENTA", 50.0, "Tipo no permitido")


# ── Tests: corte Z ────────────────────────────────────────────────────────────

def test_corte_z_solo_efectivo_en_esperado(svc, db):
    """Tarjeta y transferencia NO incrementan el efectivo esperado."""
    tid = svc.abrir_turno(1, "cajero8", 100.0)
    _insertar_venta(db, cajero="cajero8", total=200.0, forma_pago="Efectivo")
    _insertar_venta(db, cajero="cajero8", total=500.0, forma_pago="Tarjeta")
    _insertar_venta(db, cajero="cajero8", total=300.0, forma_pago="Transferencia")

    # Esperado = 100 (fondo) + 200 (efectivo) + 0 (ingresos) - 0 (retiros) = 300
    resultado = svc.generar_corte_z(tid, 1, "cajero8", 300.0)
    assert abs(resultado['efectivo_esperado'] - 300.0) < 0.01


def test_tarjeta_no_incrementa_efectivo_esperado(svc, db):
    tid = svc.abrir_turno(1, "cajero_t1", 0.0)
    _insertar_venta(db, cajero="cajero_t1", total=1000.0, forma_pago="Tarjeta")
    resultado = svc.generar_corte_z(tid, 1, "cajero_t1", 0.0)
    # Solo fondo (0) en efectivo esperado, tarjeta no cuenta
    assert abs(resultado['efectivo_esperado'] - 0.0) < 0.01


def test_transferencia_no_incrementa_efectivo_esperado(svc, db):
    tid = svc.abrir_turno(1, "cajero_t2", 50.0)
    _insertar_venta(db, cajero="cajero_t2", total=800.0, forma_pago="Transferencia")
    resultado = svc.generar_corte_z(tid, 1, "cajero_t2", 50.0)
    # Esperado = 50 (fondo solamente)
    assert abs(resultado['efectivo_esperado'] - 50.0) < 0.01


def test_corte_z_inserta_en_cierres_caja(svc, db):
    """Corte Z DEBE insertar registro en cierres_caja (historial)."""
    tid = svc.abrir_turno(1, "cajero9", 200.0)
    svc.generar_corte_z(tid, 1, "cajero9", 200.0)
    row = db.execute("SELECT COUNT(*) FROM cierres_caja").fetchone()
    assert row[0] >= 1


def test_corte_z_cierra_turno(svc, db):
    tid = svc.abrir_turno(1, "cajero10", 100.0)
    svc.generar_corte_z(tid, 1, "cajero10", 100.0)
    row = db.execute("SELECT estado FROM turnos_caja WHERE id=?", (tid,)).fetchone()
    assert row['estado'] == 'cerrado'


def test_corte_z_calcula_diferencia_faltante(svc, db):
    tid = svc.abrir_turno(1, "cajero11", 100.0)
    _insertar_venta(db, cajero="cajero11", total=200.0, forma_pago="Efectivo")
    # Esperado = 300, contado = 250 → diferencia = -50
    resultado = svc.generar_corte_z(tid, 1, "cajero11", 250.0)
    assert abs(resultado['diferencia'] - (-50.0)) < 0.01


def test_corte_z_calcula_diferencia_sobrante(svc, db):
    tid = svc.abrir_turno(1, "cajero12", 100.0)
    _insertar_venta(db, cajero="cajero12", total=200.0, forma_pago="Efectivo")
    # Esperado = 300, contado = 350 → diferencia = +50
    resultado = svc.generar_corte_z(tid, 1, "cajero12", 350.0)
    assert abs(resultado['diferencia'] - 50.0) < 0.01


def test_corte_z_turno_no_existe(svc):
    from application.services.caja_application_service import TurnoNoEncontradoError
    with pytest.raises(TurnoNoEncontradoError):
        svc.generar_corte_z(99999, 1, "nadie", 0.0)


def test_corte_z_turno_ya_cerrado(svc, db):
    from application.services.caja_application_service import TurnoCerradoError
    tid = svc.abrir_turno(1, "cajero13", 100.0)
    svc.generar_corte_z(tid, 1, "cajero13", 100.0)
    with pytest.raises(TurnoCerradoError):
        svc.generar_corte_z(tid, 1, "cajero13", 100.0)


def test_corte_z_retorna_cierre_id(svc, db):
    tid = svc.abrir_turno(1, "cajero14", 100.0)
    resultado = svc.generar_corte_z(tid, 1, "cajero14", 100.0)
    assert 'cierre_id' in resultado
    assert resultado['cierre_id'] > 0


def test_corte_z_considera_ingresos_manuales(svc, db):
    """Ingresos manuales SÍ incrementan efectivo esperado."""
    tid = svc.abrir_turno(1, "cajero15", 100.0)
    svc.registrar_movimiento_manual(tid, 1, "cajero15", "INGRESO", 200.0, "Cambio extra")
    resultado = svc.generar_corte_z(tid, 1, "cajero15", 300.0)
    # Esperado = 100 + 0 (ventas ef) + 200 (ingreso) = 300
    assert abs(resultado['efectivo_esperado'] - 300.0) < 0.01


def test_corte_z_descuenta_retiros(svc, db):
    """Retiros reducen efectivo esperado."""
    tid = svc.abrir_turno(1, "cajero16", 500.0)
    svc.registrar_movimiento_manual(tid, 1, "cajero16", "RETIRO", 100.0, "Pago a proveedor")
    resultado = svc.generar_corte_z(tid, 1, "cajero16", 400.0)
    # Esperado = 500 - 100 = 400
    assert abs(resultado['efectivo_esperado'] - 400.0) < 0.01


# ── Tests: historial ─────────────────────────────────────────────────────────

def test_historial_devuelve_cierre_recien_creado(svc, db):
    tid = svc.abrir_turno(1, "cajero17", 100.0)
    resultado = svc.generar_corte_z(tid, 1, "cajero17", 100.0)
    historial = svc.get_historial_cortes(1)
    ids = [h.get('id') for h in historial]
    assert resultado['cierre_id'] in ids


def test_historial_vacio_sin_cortes(svc):
    historial = svc.get_historial_cortes(99)  # sucursal inexistente
    assert historial == []


# ── Tests: eventos ────────────────────────────────────────────────────────────

def test_evento_corte_z_generado(svc, db):
    """CAJA_CORTE_Z_GENERADO debe publicarse al ejecutar corte."""
    eventos_capturados = []

    try:
        from core.events.event_bus import get_bus, CAJA_CORTE_Z_GENERADO
        get_bus().subscribe(
            CAJA_CORTE_Z_GENERADO,
            lambda p: eventos_capturados.append(p),
            label="test_corte_z"
        )
    except Exception:
        pytest.skip("EventBus no disponible")

    tid = svc.abrir_turno(1, "cajero18", 100.0)
    svc.generar_corte_z(tid, 1, "cajero18", 100.0)

    assert len(eventos_capturados) >= 1
    assert eventos_capturados[0].get('turno_id') == tid


def test_evento_diferencia_detectada_cuando_hay_diferencia(svc, db):
    """CAJA_DIFERENCIA_DETECTADA debe publicarse cuando diferencia != 0."""
    eventos_capturados = []

    try:
        from core.events.event_bus import get_bus, CAJA_DIFERENCIA_DETECTADA
        get_bus().subscribe(
            CAJA_DIFERENCIA_DETECTADA,
            lambda p: eventos_capturados.append(p),
            label="test_dif"
        )
    except Exception:
        pytest.skip("EventBus no disponible")

    tid = svc.abrir_turno(1, "cajero19", 100.0)
    _insertar_venta(db, cajero="cajero19", total=200.0, forma_pago="Efectivo")
    svc.generar_corte_z(tid, 1, "cajero19", 250.0)  # diferencia = -50

    assert len(eventos_capturados) >= 1
    assert abs(eventos_capturados[0].get('diferencia', 0) + 50.0) < 0.01


def test_no_evento_diferencia_cuando_cuadrado(svc, db):
    """CAJA_DIFERENCIA_DETECTADA NO debe publicarse cuando caja cuadra."""
    eventos_capturados = []

    try:
        from core.events.event_bus import get_bus, CAJA_DIFERENCIA_DETECTADA
        get_bus().subscribe(
            CAJA_DIFERENCIA_DETECTADA,
            lambda p: eventos_capturados.append(p),
            label="test_no_dif"
        )
    except Exception:
        pytest.skip("EventBus no disponible")

    tid = svc.abrir_turno(1, "cajero20", 100.0)
    svc.generar_corte_z(tid, 1, "cajero20", 100.0)  # cuadrado

    assert len(eventos_capturados) == 0


# ── Tests: UI no contiene self.container.db.execute ──────────────────────────

def test_ui_no_contiene_db_execute_directo():
    """Verifica que modulos/caja.py no tenga SQL directo."""
    import ast
    caja_path = os.path.join(os.path.dirname(__file__), "..", "modulos", "caja.py")
    with open(caja_path, "r") as f:
        source = f.read()

    # Buscar patrones de acceso directo a DB en la UI
    patrones_prohibidos = [
        "self.container.db.execute",
        "container.db.execute(",
    ]
    for patron in patrones_prohibidos:
        assert patron not in source, (
            f"modulos/caja.py contiene SQL directo: '{patron}'. "
            "Debe delegarse a caja_service."
        )


def test_caja_py_sintaxis_valida():
    """modulos/caja.py debe tener sintaxis Python válida."""
    import ast
    caja_path = os.path.join(os.path.dirname(__file__), "..", "modulos", "caja.py")
    with open(caja_path, "r") as f:
        source = f.read()
    ast.parse(source)  # raises SyntaxError si hay problema
