"""Compras: una sola fuente de verdad para la condición financiera.

La condición (Liquidado/Crédito/Parcial) vive SOLO en _cmb_condicion_pago;
el método de pago no vuelve a declarar el crédito ni usa Caja POS.
Validación estática (el entorno CI no tiene PyQt5); la validación visual
se hace en el checklist manual.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "modulos" / "compras_pro.py").read_text(encoding="utf-8")


def test_payment_items_do_not_duplicate_credit():
    bloque = SRC.split("_PAGO_ITEMS = [", 1)[1].split("]", 1)[0]
    assert "CREDITO" not in bloque, (
        "El crédito es una CONDICIÓN, no un método: no debe estar en _PAGO_ITEMS"
    )
    assert "CAJA" not in bloque.upper(), "Caja POS no es origen de pago de compras"


def test_single_condition_combo():
    assert SRC.count("self._cmb_condicion_pago = ") == 1
    assert SRC.count("self.cmb_pago = ") == 1


def test_consumers_use_canonical_derivation():
    assert "def _payment_method(self)" in SRC
    assert 'self.cmb_pago.currentData() or "CONTADO"' not in SRC.replace(
        'return (self.cmb_pago.currentData() or "CONTADO")', ""
    ), "los consumidores deben derivar el método con _payment_method()"
    assert SRC.count("self._payment_method()") >= 2


def test_no_hardcoded_30_day_default():
    assert not re.search(r"_spin_plazo_dias\.setValue\(\s*30\s*\)", SRC), (
        "prohibido default arbitrario 30 (regla 23) — el plazo inicia en 0"
    )


def test_credit_condition_disables_payment_method():
    assert "es_credito_total" in SRC
    assert "self.cmb_pago.setEnabled(not es_credito_total)" in SRC
