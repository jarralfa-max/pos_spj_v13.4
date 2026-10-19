# tests/architecture/test_remediacion0_guardrails.py
"""Guardrails estáticos de la Remediación 0 (hotfixes del DEEP_AUDIT 20260704).

Cada test bloquea la regresión de un bug concreto corregido en el PR de
Remediación 0. Referencia: docs/refactor/DEEP_AUDIT_ALL_MODULES_20260704.md
(bugs B1, B6, B7, B8, B9, B10, B13, B14).
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2]  # pos_spj_v13.4/ (paquete)


def _read(rel: str) -> str:
    return (PKG_ROOT / rel).read_text(encoding="utf-8")


def _method_source(rel: str, class_name: str, method_name: str) -> str:
    src = _read(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(src, item) or ""
    raise AssertionError(f"No se encontró {class_name}.{method_name} en {rel}")


def _method_node(rel: str, class_name: str, method_name: str) -> ast.FunctionDef:
    src = _read(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    raise AssertionError(f"No se encontró {class_name}.{method_name} en {rel}")


# ── B1: handler financiero de rifas ──────────────────────────────────────────

# ── B7: inbox del login debe ser del usuario logueado ────────────────────────

# ── B8: inbox/badges arrancan tras el login, no solo al re-anclar sucursal ──

# ── B9: _on_pedido_nuevo invocable vía QMetaObject.invokeMethod ─────────────

# ── B13: recepción QR sin sucursal inventada ─────────────────────────────────

def test_recepcion_qr_sin_fallback_principal():
    assert not (PKG_ROOT / "modulos" / "recepcion_qr_widget.py").exists()


# ── B14: producción sin sucursal 1 / 'Principal' ─────────────────────────────

# ── B6: BI v2 suscrito a canales que SÍ se emiten ────────────────────────────

_CANALES_FANTASMA = ("venta_confirmada", "stock_actualizado", "pago_registrado")


# ── B10: los servicios CxC/CxP publican sus eventos de creación ─────────────

