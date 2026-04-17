# tests/test_uc_cliente.py — SPJ POS v13.5
"""Tests unitarios para GestionarClienteUC."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock

from core.use_cases.cliente import (
    GestionarClienteUC, DatosCliente, ResultadoCliente,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_uc(repo_crear_return=1, repo_existe=True):
    repo = MagicMock()
    repo.crear.return_value = repo_crear_return
    repo.actualizar.return_value = True
    repo.dar_de_baja.return_value = True
    repo.existe = MagicMock(return_value=repo_existe)

    finance = MagicMock()
    finance.registrar_asiento.return_value = 77

    loyalty = MagicMock()
    loyalty.registrar_en_ledger.return_value = None

    bus = MagicMock()

    uc = GestionarClienteUC(
        cliente_repo    = repo,
        loyalty_service = loyalty,
        finance_service = finance,
        event_bus       = bus,
    )
    return uc, repo, finance, loyalty, bus


def _datos(nombre="Juan Pérez", allows_credit=False, credit_limit=0.0):
    return DatosCliente(
        nombre=nombre,
        telefono="5551234567",
        allows_credit=allows_credit,
        credit_limit=credit_limit,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCrearCliente:

    def test_nombre_vacio_retorna_error(self):
        uc, *_ = _make_uc()
        res = uc.crear_cliente(_datos(nombre=""), sucursal_id=1, usuario="admin")
        assert res.ok is False
        assert "nombre" in res.error.lower() or "obligatorio" in res.error.lower()

    def test_nombre_espacios_retorna_error(self):
        uc, *_ = _make_uc()
        res = uc.crear_cliente(_datos(nombre="   "), sucursal_id=1, usuario="admin")
        assert res.ok is False

    def test_crear_sin_credito_no_llama_asiento(self):
        uc, _, finance, *_ = _make_uc()
        uc.crear_cliente(_datos(allows_credit=False, credit_limit=0), sucursal_id=1, usuario="a")
        finance.registrar_asiento.assert_not_called()

    def test_crear_con_credito_llama_asiento_apertura(self):
        uc, _, finance, *_ = _make_uc()
        uc.crear_cliente(_datos(allows_credit=True, credit_limit=5000.0), sucursal_id=1, usuario="a")
        finance.registrar_asiento.assert_called_once()
        kwargs = finance.registrar_asiento.call_args.kwargs
        assert kwargs.get("debe") == "1301"
        assert kwargs.get("haber") == "3101"
        assert kwargs.get("monto") == 5000.0

    def test_crear_publica_evento_cliente_creado(self):
        uc, _, _, _, bus = _make_uc()
        uc.crear_cliente(_datos(), sucursal_id=1, usuario="a")
        bus.publish.assert_called_once()
        evento = bus.publish.call_args[0][0]
        assert evento == "CLIENTE_CREADO"

    def test_loyalty_falla_creacion_continua(self):
        uc, _, _, loyalty, _ = _make_uc()
        loyalty.registrar_en_ledger.side_effect = Exception("ledger error")
        res = uc.crear_cliente(_datos(), sucursal_id=1, usuario="a")
        assert res.ok is True
        assert res.cliente_id == 1


class TestActualizarCliente:

    def test_actualizar_inexistente_retorna_error(self):
        uc, *_ = _make_uc(repo_existe=False)
        res = uc.actualizar_cliente(999, {"nombre": "Nuevo"}, usuario="a")
        assert res.ok is False
        assert "999" in res.error or "encontrado" in res.error.lower()

    def test_actualizar_publica_evento_actualizado(self):
        uc, _, _, _, bus = _make_uc(repo_existe=True)
        uc.actualizar_cliente(1, {"telefono": "5559999999"}, usuario="a")
        bus.publish.assert_called_once()
        evento = bus.publish.call_args[0][0]
        assert evento == "CLIENTE_ACTUALIZADO"


class TestDarDeBaja:

    def test_dar_de_baja_retorna_ok(self):
        uc, *_ = _make_uc()
        res = uc.dar_de_baja(1, usuario="admin")
        assert res.ok is True

    def test_dar_de_baja_publica_evento(self):
        uc, _, _, _, bus = _make_uc()
        uc.dar_de_baja(1, usuario="admin")
        bus.publish.assert_called_once()
        payload = bus.publish.call_args[0][1]
        assert payload.get("accion") == "baja"
