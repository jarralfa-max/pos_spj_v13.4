"""Fase 5 (2026-09-18) — las pantallas de precio mínimo y canal.

- El descuento del mostrador tenía permiso, caso de uso y diálogo, pero ningún
  botón ni atajo lo abría.
- El diálogo pedía el UUID del autorizador, sin clave, y un rechazo no decía
  nada.
- El canal de una lista de precios era texto libre que nunca coincidía con el
  código con que Ventas y Pedidos piden precio.
"""

from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)

from backend.application.sales.permissions import SalesPermissions  # noqa: E402
from backend.domain.pricing.enums import SALE_CHANNELS  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


# ── botón de descuento ─────────────────────────────────────────────────────
class _Sesion:
    def __init__(self, permisos):
        self.user_id = "cajero"
        self.active_branch_id = "sucursal"
        self.is_active = True
        self._permisos = set(permisos)

    def tiene_permiso(self, code):
        return code in self._permisos


def _workspace(permisos):
    from frontend.desktop.modules.sales_pos.sales_pos_presenter import SalesPosPresenter
    from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace
    return SalesPosWorkspace(SalesPosPresenter(session_context=_Sesion(permisos)))


def _todos():
    return {p for p in vars(SalesPermissions).values() if isinstance(p, str)}


def test_el_boton_de_descuento_sigue_al_permiso(app):
    assert _workspace(_todos()).checkout.actions.btn_descuento.isEnabled() is True
    sin = _todos() - {SalesPermissions.DISCOUNT_APPLY}
    assert _workspace(sin).checkout.actions.btn_descuento.isEnabled() is False


def test_el_boton_y_f5_abren_el_dialogo_de_descuento(app, monkeypatch):
    import frontend.desktop.modules.sales_pos.sales_pos_workspace as modulo

    abiertos = []

    class _Dialogo:
        applied = False

        def __init__(self, presenter, *, sale_id, parent=None):
            abiertos.append(sale_id)

        def exec_(self):
            return 0

    monkeypatch.setattr(modulo, "DiscountDialog", _Dialogo)
    ws = _workspace(_todos())
    ws._sale_id = "venta-1"

    ws.checkout.actions.btn_descuento.click()
    [f5] = [s for s in ws._shortcuts if s.key().toString() == "F5"]
    f5.activated.emit()

    assert abiertos == ["venta-1", "venta-1"]


# ── diálogo de descuento ───────────────────────────────────────────────────
class _Presentador:
    def __init__(self, *, autorizador=("gerente-id", ""), resultado=None):
        self.autorizador = autorizador
        self.resultado = resultado or SimpleNamespace(success=True, message="ok")
        self.verificados = []
        self.aplicados = []

    def verify_authorizer(self, usuario, clave):
        self.verificados.append((usuario, clave))
        return self.autorizador

    def apply_sale_discount(self, **kwargs):
        self.aplicados.append(kwargs)
        return self.resultado


def _dialogo(presentador):
    from frontend.desktop.modules.sales_pos.dialogs.discount_dialog import DiscountDialog
    return DiscountDialog(presentador, sale_id="venta-1")


def test_sin_autorizador_aplica_el_descuento_sin_verificar(app):
    p = _Presentador()
    d = _dialogo(p)
    d._amount.set_decimal_value("5")

    d._submit()

    assert p.verificados == []
    assert p.aplicados[0]["authorizer_user_id"] is None
    assert p.aplicados[0]["discount_amount"] == Decimal("5")
    assert d.applied is True


def test_el_autorizador_se_verifica_con_su_clave_antes_de_aplicar(app):
    p = _Presentador()
    d = _dialogo(p)
    d._amount.set_decimal_value("10")
    d._authorizer.setText("gerente")
    d._password.setText("secreta")
    d._reason.setText("cliente frecuente")

    d._submit()

    assert p.verificados == [("gerente", "secreta")]
    assert p.aplicados[0]["authorizer_user_id"] == "gerente-id"
    assert p.aplicados[0]["reason"] == "cliente frecuente"


def test_una_clave_mala_no_aplica_nada_y_lo_dice(app):
    p = _Presentador(autorizador=(None, "Usuario o contraseña del autorizador incorrectos."))
    d = _dialogo(p)
    d._amount.set_decimal_value("10")
    d._authorizer.setText("gerente")
    d._password.setText("mala")

    d._submit()

    assert p.aplicados == []
    assert d.applied is False
    assert "incorrectos" in d._status.text()
    assert d._status.isHidden() is False


def test_un_rechazo_del_caso_de_uso_se_muestra(app):
    """Antes un fallo (bajo el mínimo, sin autorización) no mostraba nada."""
    p = _Presentador(resultado=SimpleNamespace(
        success=False, message="El descuento deja el precio bajo el mínimo"))
    d = _dialogo(p)
    d._amount.set_decimal_value("10")

    d._submit()

    assert d.applied is False
    assert "bajo el mínimo" in d._status.text()


# ── canal de la lista de precios ───────────────────────────────────────────
def _lista():
    from frontend.desktop.modules.pricing.dialogs.pricing_dialogs import PriceListFormDialog
    return PriceListFormDialog()


def test_el_canal_se_elige_de_los_canales_de_venta(app):
    d = _lista()
    assert [d._channel.itemData(i) for i in range(d._channel.count())
            if d._channel.itemData(i)] == list(SALE_CHANNELS)


def test_una_lista_de_canal_exige_elegir_el_canal(app):
    d = _lista()
    d._code.setText("WA")
    d._name.setText("WhatsApp")
    d._kind.set_current_id("CHANNEL")

    assert "canal" in d._error()

    d._channel.set_current_id("WHATSAPP")
    assert d._error() is None
    assert d.values()["channel"] == "WHATSAPP"


def test_el_canal_no_viaja_en_listas_que_no_son_de_canal(app):
    d = _lista()
    d._code.setText("BASE")
    d._name.setText("Base")
    d._kind.set_current_id("BASE")
    d._channel.set_current_id("WHATSAPP")

    assert d.values()["channel"] is None
