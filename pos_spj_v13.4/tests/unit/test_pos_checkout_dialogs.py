"""Fase 6 (2026-09-18) — la pantalla de cobro con las reglas nuevas.

- Sin turno de caja se avisa ANTES de abrir el cobro: una vez registrados los
  pagos, la venta ya no vuelve al carrito.
- Reintentar tras un fallo no inicia otra vez el cobro ni duplica pagos.
- Sin existencia, el cobro ofrece la autorización en caliente (usuario, clave,
  motivo) y reintenta con el autorizador verificado.
"""
from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ok(**data):
    return SimpleNamespace(success=True, message="ok", error_code=None, data=data)


def _fail(code, message="no"):
    return SimpleNamespace(success=False, message=message, error_code=code, data={})


class _Presentador:
    def __init__(self, cobros, *, autorizador=("gerente-id", "")):
        self.cobros = list(cobros)
        self.autorizador = autorizador
        self.llamadas = []

    def begin_checkout(self, **kw):
        self.llamadas.append(("begin", kw))
        return _ok()

    def record_payment(self, **kw):
        self.llamadas.append(("pago", kw))
        return _ok()

    def checkout_sale(self, **kw):
        self.llamadas.append(("cobrar", kw))
        return self.cobros.pop(0)

    def verify_authorizer(self, usuario, clave):
        return self.autorizador


def _pago(presentador):
    from frontend.desktop.modules.sales_pos.dialogs.payment_dialog import PaymentDialog
    d = PaymentDialog(presentador, sale_id="v1", total_due=Decimal("100"))
    d._lines = [("CASH", Decimal("100"), None)]
    return d


def _pasos(p, nombre):
    return [kw for paso, kw in p.llamadas if paso == nombre]


def test_reintentar_el_cobro_no_duplica_pagos(app, monkeypatch):
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    p = _Presentador([_fail("NO_OPEN_CASH_SHIFT"), _ok()])
    d = _pago(p)

    d._confirm()
    d._confirm()

    assert len(_pasos(p, "begin")) == 1
    assert len(_pasos(p, "pago")) == 1
    assert len(_pasos(p, "cobrar")) == 2
    assert d.completed is True


def test_sin_existencia_ofrece_autorizar_y_reintenta_con_el_autorizador(app, monkeypatch):
    import frontend.desktop.modules.sales_pos.dialogs.stock_authorization_dialog as modulo

    class _Autoriza:
        def __init__(self, presenter, *, message, parent=None):
            self.authorizer_user_id, self.reason = "gerente-id", "llega mercancía"

        def exec_(self):
            return 1

    monkeypatch.setattr(modulo, "StockAuthorizationDialog", _Autoriza)
    p = _Presentador([_fail("STOCK_AUTHORIZATION_REQUIRED", "disponible 8"), _ok()])
    d = _pago(p)

    d._confirm()

    segundo = _pasos(p, "cobrar")[1]
    assert (segundo["authorizer_user_id"], segundo["reason"]) == ("gerente-id", "llega mercancía")
    assert d.completed is True


def _autorizacion(presentador):
    from frontend.desktop.modules.sales_pos.dialogs.stock_authorization_dialog import (
        StockAuthorizationDialog,
    )
    return StockAuthorizationDialog(presentador, message="disponible 8, se venden 20")


def test_la_autorizacion_exige_motivo(app):
    d = _autorizacion(_Presentador([]))
    d._user.setText("gerente")
    d._password.setText("clave")

    d._authorize()

    assert d.authorizer_user_id is None
    assert "motivo" in d._status.text()


def test_una_clave_mala_no_autoriza(app):
    d = _autorizacion(_Presentador([], autorizador=(None, "Usuario o contraseña incorrectos.")))
    d._user.setText("gerente")
    d._password.setText("mala")
    d._reason.setText("urgente")

    d._authorize()

    assert d.authorizer_user_id is None
    assert "incorrectos" in d._status.text()


def test_autoriza_con_el_usuario_verificado(app):
    d = _autorizacion(_Presentador([]))
    d._user.setText("gerente")
    d._password.setText("clave")
    d._reason.setText("urgente")

    d._authorize()

    assert (d.authorizer_user_id, d.reason) == ("gerente-id", "urgente")


def test_sin_turno_el_cobro_ni_siquiera_se_abre(app, monkeypatch):
    from backend.application.sales.permissions import SalesPermissions
    from frontend.desktop.modules.sales_pos import sales_pos_workspace as ws_mod
    from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter

    class _Sesion:
        user_id, active_branch_id, is_active = "cajero", "sucursal", True

        def tiene_permiso(self, code):
            return code in {p for p in vars(SalesPermissions).values() if isinstance(p, str)}

    avisos, abiertos = [], []
    monkeypatch.setattr(ws_mod.QMessageBox, "warning", lambda *a, **k: avisos.append(a[2]))
    monkeypatch.setattr(ws_mod, "PaymentDialog", lambda *a, **k: abiertos.append(1))
    presenter = SalesPosPresenter(
        session_context=_Sesion(),
        query_services={"sale_query": SimpleNamespace(
                            get=lambda sale_id, requester_user_id: SimpleNamespace(
                                total=Decimal("100"), lines=[1])),
                        "cash_shift": lambda **kw: "No tienes un turno de caja abierto."})
    ws = ws_mod.SalesPosWorkspace(presenter)
    ws._sale_id = "v1"

    ws._on_checkout_requested()

    assert abiertos == []
    assert avisos == ["No tienes un turno de caja abierto."]
