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

def test_wiring_no_compara_raffle_id_str_con_int():
    src = _read("core/events/wiring.py")
    assert "if raffle_id <= 0" not in src, (
        "B1: reapareció `raffle_id <= 0` sobre un str — TypeError silencioso "
        "que impide registrar los asientos de rifas."
    )


# ── B7: inbox del login debe ser del usuario logueado ────────────────────────

def test_inbox_login_filtra_por_usuario():
    body = _method_source("interfaz/main_window.py", "MainWindow", "_mostrar_inbox_login")
    assert "usuario_id" in body and "WHERE usuario_id=?" in body.replace("  ", " "), (
        "B7: _mostrar_inbox_login debe buscar el empleado vinculado al usuario "
        "logueado (personal.usuario_id), no el primer empleado activo."
    )
    assert "WHERE activo=1 LIMIT 1" not in body, (
        "B7: query sin filtro de usuario — muestra/marca leído el inbox de "
        "OTRO empleado."
    )


# ── B8: inbox/badges arrancan tras el login, no solo al re-anclar sucursal ──

def test_badges_e_inbox_arrancan_en_propagar_usuario():
    body = _method_source("interfaz/main_window.py", "MainWindow", "_propagar_usuario")
    assert "_start_badge_refresh" in body and "_mostrar_inbox_login" in body, (
        "B8: _propagar_usuario (ruta de login) debe agendar "
        "_mostrar_inbox_login y _start_badge_refresh."
    )


def test_aplicar_sucursal_activa_no_arranca_inbox():
    body = _method_source("interfaz/main_window.py", "MainWindow", "aplicar_sucursal_activa")
    assert "_mostrar_inbox_login" not in body, (
        "B8: el arranque del inbox no debe vivir en aplicar_sucursal_activa "
        "(solo corre al re-anclar sucursal desde Configuración)."
    )


# ── B9: _on_pedido_nuevo invocable vía QMetaObject.invokeMethod ─────────────

def test_on_pedido_nuevo_es_pyqtslot():
    node = _method_node("interfaz/main_window.py", "MainWindow", "_on_pedido_nuevo")
    decoradores = [ast.unparse(d) for d in node.decorator_list]
    assert any("pyqtSlot" in d for d in decoradores), (
        "B9: _on_pedido_nuevo debe estar decorado con @pyqtSlot para que "
        "QMetaObject.invokeMethod lo encuentre; sin él, el badge de pedidos "
        "no reacciona al evento PEDIDO_NUEVO."
    )


# ── B13: recepción QR sin sucursal inventada ─────────────────────────────────

def test_recepcion_qr_sin_fallback_principal():
    src = _read("modulos/recepcion_qr_widget.py")
    assert 'addItem("Principal", 1)' not in src and "addItem('Principal', 1)" not in src, (
        "B13: reapareció el fallback hardcodeado a sucursal 'Principal'/1 en "
        "el combo de recepción QR."
    )


# ── B14: producción sin sucursal 1 / 'Principal' ─────────────────────────────

def test_produccion_sin_sucursal_uno():
    src = _read("modulos/produccion.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # self.sucursal_id = 1
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and node.value.value == 1:
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "sucursal_id":
                    raise AssertionError("B14: `self.sucursal_id = 1` reapareció en produccion.py")
        # RecipeEngine(..., branch_id=1)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "branch_id" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value == 1:
                    raise AssertionError("B14: `branch_id=1` reapareció en produccion.py")
    assert 'self.sucursal_nombre = "Principal"' not in src, (
        "B14: fallback 'Principal' reapareció en produccion.py"
    )


# ── B6: BI v2 suscrito a canales que SÍ se emiten ────────────────────────────

_CANALES_FANTASMA = ("venta_confirmada", "stock_actualizado", "pago_registrado")


def test_bi_v2_no_escucha_canales_fantasma():
    node = _method_node("modulos/reportes_bi_v2.py", "ModuloReportesBIv2",
                        "_wire_business_events")
    # Canales por los que itera el for de suscripción (literales y constantes).
    suscritos_literales: set = set()
    suscritos_constantes: set = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.For) and isinstance(sub.iter, ast.Tuple):
            for elt in sub.iter.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    suscritos_literales.add(elt.value)
                elif isinstance(elt, ast.Name):
                    suscritos_constantes.add(elt.id)
    for canal in _CANALES_FANTASMA:
        assert canal not in suscritos_literales, (
            f"B6: BI v2 sigue suscrito al canal fantasma '{canal}' que nadie "
            "emite — el dashboard no se refresca en caliente."
        )
    for constante in ("VENTA_COMPLETADA", "MOVIMIENTO_FINANCIERO"):
        assert constante in suscritos_constantes, (
            f"B6: BI v2 debe suscribirse a {constante} (canal real del bus)."
        )


# ── B10: los servicios CxC/CxP publican sus eventos de creación ─────────────

def test_accounts_services_publican_eventos():
    ar = _read("core/services/finance/accounts_receivable_service.py")
    ap = _read("core/services/finance/accounts_payable_service.py")
    assert "ACCOUNT_RECEIVABLE_CREATED" in ar and ".publish(" in ar, (
        "B10: crear_cxc debe publicar CXC_CREADA al bus (la UI de Finanzas "
        "está suscrita a ese canal)."
    )
    assert "ACCOUNT_PAYABLE_CREATED" in ap and ".publish(" in ap, (
        "B10: crear_cxp debe publicar CXP_CREADA al bus."
    )
