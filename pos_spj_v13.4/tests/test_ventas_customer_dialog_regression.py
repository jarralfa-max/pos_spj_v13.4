# tests/test_ventas_customer_dialog_regression.py — SPJ ERP v13.4
"""
Regression coverage for ModuloVentas' checkout-customer methods
(`guardar_nuevo_cliente`, `buscar_cliente`) BEFORE CRM-25 touches them.

These call the real bound methods on `ModuloVentas` without constructing a
real QWidget (PyQt5 construction needs a live QApplication and is unrelated
to what these methods actually do) — a plain `types.SimpleNamespace` stands
in for `self`, carrying only the attributes each method reads. This is a
duck-typed unbound-method call, valid Python: `ModuloVentas.method(fake_self, ...)`
never checks `isinstance(fake_self, ModuloVentas)`.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

from modulos.ventas import ModuloVentas
from repositories.cliente_repository import ClienteRepository
from backend.application.use_cases.create_customer_use_case import CreateCustomerUseCase
from core.services.sales.customer_lookup_service import CustomerLookupService


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            direccion TEXT,
            notas TEXT,
            rfc TEXT,
            puntos REAL DEFAULT 0,
            nivel TEXT,
            nivel_fidelidad TEXT,
            codigo_qr TEXT,
            codigo_fidelidad TEXT,
            saldo REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            fecha_alta TEXT
        );
        CREATE TABLE tarjetas_fidelidad (
            codigo TEXT PRIMARY KEY,
            id_cliente TEXT,
            nivel TEXT,
            activa INTEGER DEFAULT 1,
            fecha_emision TEXT
        );
        """
    )
    conn.commit()
    return conn


def _fake_ventas(conn):
    cli_repo = ClienteRepository(conn)
    ns = SimpleNamespace()
    ns.conexion = conn
    ns._cli_repo = cli_repo
    ns._create_customer_uc = CreateCustomerUseCase(conn, cli_repo)
    ns._customer_lookup_svc = CustomerLookupService(conn)
    ns.cliente_actual = None
    ns.actualizar_info_cliente = MagicMock()
    ns.mostrar_mensaje = MagicMock()
    ns.limpiar_cliente = MagicMock(side_effect=lambda: setattr(ns, "cliente_actual", None))
    ns._bridge_customer_to_crm = lambda cid: ModuloVentas._bridge_customer_to_crm(ns, cid)
    return ns


class TestGuardarNuevoClienteRegression:
    """`guardar_nuevo_cliente` must select the freshly created/matched
    customer with a real UUID string id — never crash with an int() cast
    on a UUID, never call a method that doesn't exist on the class."""

    def test_new_customer_is_created_and_selected(self):
        conn = _make_db()
        ns = _fake_ventas(conn)

        ModuloVentas.guardar_nuevo_cliente(ns, {
            "nombre": "Ana Torres",
            "telefono": "5512345678",
            "email": "",
            "direccion": "",
            "generar_tarjeta": False,
            "tarjeta_id": "",
        })

        # Must not have reported an error.
        error_calls = [c for c in ns.mostrar_mensaje.call_args_list if "Error" in str(c)]
        assert not error_calls, f"guardar_nuevo_cliente reported an error: {error_calls}"

        assert ns.cliente_actual is not None, "cliente_actual was never set"
        assert isinstance(ns.cliente_actual["id"], str), (
            "cliente_actual['id'] must stay a UUID string, not be int()-cast"
        )
        row = conn.execute("SELECT nombre FROM clientes WHERE id=?", (ns.cliente_actual["id"],)).fetchone()
        assert row is not None and row["nombre"] == "Ana Torres"
        ns.actualizar_info_cliente.assert_called_once()

    def test_existing_customer_via_loyalty_card_is_selected_not_errored(self):
        """Assigning a card already bound to a customer must re-select that
        customer, not raise (previously: AttributeError from calling a
        non-existent `self.seleccionar_cliente`, masked by an int() crash
        that fired first)."""
        conn = _make_db()
        ns = _fake_ventas(conn)

        # First creation binds the loyalty card to a new customer.
        ModuloVentas.guardar_nuevo_cliente(ns, {
            "nombre": "Beto Ruiz", "telefono": "5599998888", "email": "",
            "direccion": "", "generar_tarjeta": True, "tarjeta_id": "TAR-001",
        })
        first_id = ns.cliente_actual["id"]
        ns.cliente_actual = None
        ns.actualizar_info_cliente.reset_mock()
        ns.mostrar_mensaje.reset_mock()

        # Second attempt with the SAME card id must resolve to the existing customer.
        ModuloVentas.guardar_nuevo_cliente(ns, {
            "nombre": "Beto Ruiz (dup form entry)", "telefono": "", "email": "",
            "direccion": "", "generar_tarjeta": True, "tarjeta_id": "TAR-001",
        })

        error_calls = [c for c in ns.mostrar_mensaje.call_args_list if "Error" in str(c)]
        assert not error_calls, f"guardar_nuevo_cliente reported an error: {error_calls}"
        assert ns.cliente_actual is not None, "existing-card branch never set cliente_actual"
        assert ns.cliente_actual["id"] == first_id, "existing-card branch selected the wrong customer"


class TestBuscarClienteBaseline:
    """Baseline for `buscar_cliente`'s found path, before CRM-25 step 5
    swaps its lookup source — must keep working identically."""

    def test_found_customer_populates_cliente_actual(self):
        conn = _make_db()
        cli_repo = ClienteRepository(conn)
        real_id = cli_repo.crear(nombre="Carla Diaz", telefono="5511112222")

        ns = _fake_ventas(conn)
        ns.txt_cliente = MagicMock()
        ns.txt_cliente.text.return_value = "Carla"

        ModuloVentas.buscar_cliente(ns)

        assert ns.cliente_actual is not None, "existing customer search found nothing"
        assert ns.cliente_actual["id"] == real_id
        assert ns.cliente_actual["nombre"] == "Carla Diaz"
        ns.txt_cliente.clear.assert_called_once()
