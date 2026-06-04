import os
import sqlite3
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pos_spj_v13.4"))

FORBIDDEN_TOKENS = [
    "crear_tab_fidelizacion",
    "crear_tab_hardware",
    "crear_tab_ticket_designer",
    "_setup_tab_whatsapp",
    "_toggle_dark_mode",
    "DialogoUsuario",
    "tabla_usuarios",
]


def _minimal_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT, descripcion TEXT);
        CREATE TABLE sucursales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            direccion TEXT,
            telefono TEXT,
            activa INTEGER DEFAULT 1,
            hora_apertura TEXT,
            hora_cierre TEXT,
            dias_operacion TEXT,
            acepta_pedidos_fuera_horario INTEGER DEFAULT 0,
            mensaje_fuera_horario TEXT
        );
        CREATE TABLE usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, nombre TEXT, email TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER DEFAULT 1, empleado_id INTEGER, password_hash TEXT);
        CREATE TABLE roles(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, descripcion TEXT);
        CREATE TABLE rol_permisos(rol_id INTEGER, modulo TEXT, accion TEXT, permitido INTEGER);
        CREATE TABLE personal(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, apellidos TEXT, activo INTEGER DEFAULT 1, usuario_id INTEGER);
        CREATE TABLE audit_logs(fecha TEXT, usuario TEXT, modulo TEXT, accion TEXT, detalles TEXT);
        CREATE TABLE cierre_mensual(periodo TEXT, cerrado_por TEXT, fecha_cierre TEXT, total_ventas REAL, total_compras REAL, total_merma REAL);
        CREATE TABLE happy_hour_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, hora_inicio TEXT, hora_fin TEXT, dias_semana TEXT, tipo_descuento TEXT, valor REAL, aplica_a TEXT, aplica_valor TEXT, mensaje_wa TEXT, activo INTEGER, sucursal_id INTEGER);
        INSERT INTO sucursales(nombre, direccion, telefono, activa) VALUES('Principal', 'Centro', '+5215512345678', 1);
        INSERT INTO rol_permisos(rol_id, modulo, accion, permitido) VALUES(1, 'CONFIGURACION', 'ver', 1);
        INSERT INTO roles(nombre, descripcion) VALUES('admin', 'Administrador');
        """
    )
    return conn


def test_settings_module_imports_without_forbidden_sections() -> None:
    content = (REPO_ROOT / "pos_spj_v13.4" / "modulos" / "configuracion.py").read_text(encoding="utf-8")
    assert not [token for token in FORBIDDEN_TOKENS if token in content]


def test_modulo_configuracion_loads_with_canonical_sections() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt5.QtWidgets import QApplication
        from modulos.configuracion import ModuloConfiguracion
    except ImportError as exc:
        pytest.skip(f"PyQt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    module = ModuloConfiguracion(_minimal_connection())

    labels = [module._nav_list.item(index).text() for index in range(module._nav_list.count())]
    assert labels == [
        "🏢 Empresa / Fiscal",
        "👤 Usuarios y Roles",
        "📧 Email / SMTP",
        "💳 Mercado Pago",
        "⏰ Happy Hour",
        "📅 Cierre Mensual",
    ]
    module.deleteLater()
    app.processEvents()
