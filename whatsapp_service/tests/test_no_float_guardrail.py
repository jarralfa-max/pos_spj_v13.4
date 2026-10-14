# tests/test_no_float_guardrail.py — PROD-22 (decisión del usuario 2026-10-10:
# «todo el microservicio a Decimal»)
"""Ningún `float` en el código del microservicio WhatsApp.

Dinero, cantidades, existencias, pesos, porcentajes y puntajes viajan como
`Decimal` (`domain/money.py`); tiempos y plazos como enteros (segundos o ns).
La guarda lee los tokens de Python, así que comentarios y docstrings que
mencionan la palabra no cuentan.
"""
from __future__ import annotations

import io
import json
import tokenize
from decimal import Decimal
from pathlib import Path

from domain.money import dumps_decimal, loads_decimal, quantize_money, to_decimal

ROOT = Path(__file__).resolve().parents[1]


def _offenders():
    out = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("tests/") or "__pycache__" in rel or "/.venv/" in f"/{rel}":
            continue
        source = path.read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.NAME and tok.string == "float":
                out.append(f"{rel}:{tok.start[0]}: float")
            elif tok.type == tokenize.NUMBER and not tok.string.lower().startswith("0x") \
                    and any(c in tok.string.lower() for c in ".e") and not tok.string.endswith("j"):
                out.append(f"{rel}:{tok.start[0]}: literal {tok.string}")
    return out


def test_no_float_anywhere_in_service_code():
    offenders = _offenders()
    assert not offenders, "float en el microservicio:\n" + "\n".join(offenders)


def test_to_decimal_goes_through_text():
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal("2,5") == Decimal("2.5")
    assert to_decimal(None) == Decimal("0")
    assert to_decimal("abc", default="1") == Decimal("1")


def test_money_rounds_half_up():
    assert quantize_money("2.675") == Decimal("2.68")
    assert quantize_money("0.125") == Decimal("0.13")


def test_json_roundtrip_is_exact_and_numeric():
    text = dumps_decimal({"total": Decimal("1234.50"), "items": [Decimal("-0.1"), "x"], "n": 1})
    assert json.loads(text) == {"total": 1234.5, "items": [-0.1, "x"], "n": 1}  # número, no texto
    back = loads_decimal(text)
    assert back["total"] == Decimal("1234.50") and isinstance(back["total"], Decimal)
    assert isinstance(back["items"][0], Decimal) and back["n"] == 1


def test_persisted_context_item_comes_back_as_decimal():
    from models.context import PedidoItem
    item = PedidoItem.from_dict({"producto_id": "p", "nombre": "Pechuga",
                                 "cantidad": "1.5", "precio_unitario": 120.1})
    assert item.cantidad == Decimal("1.5") and item.precio_unitario == Decimal("120.1")
    assert item.subtotal == Decimal("180.15")
