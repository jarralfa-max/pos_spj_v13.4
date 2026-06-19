"""Architecture tests for the Delivery module.

These tests act as guard-rails: they FAIL if someone reintroduces
duplicate routes, direct SQL in UI, or transactions in UI.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
DELIVERY_UI = ROOT / "modulos" / "delivery.py"
DELIVERY_SERVICE = ROOT / "core" / "services" / "delivery_service.py"
CHANGE_STATUS_UC = ROOT / "core" / "delivery" / "application" / "change_delivery_status.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ast(path: Path) -> ast.Module:
    return ast.parse(_source(path))


# ── 1. No direct estado UPDATE in UI ─────────────────────────────────────────

def test_no_direct_estado_update_in_delivery_ui():
    """delivery.py must not run UPDATE delivery_orders SET estado= directly."""
    src = _source(DELIVERY_UI)
    # Allow the pattern only inside comments
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"UPDATE\s+delivery_orders\s+SET\s+estado", line, re.IGNORECASE):
            raise AssertionError(
                f"Direct estado UPDATE found in delivery.py line {lineno}:\n  {line.strip()}"
            )


# ── 2. No db.commit / conexion.commit in delivery UI ─────────────────────────

def test_no_commit_in_delivery_ui():
    """The UI layer must never call commit(); that belongs to the use-case layer."""
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\.(commit|rollback)\s*\(", line):
            raise AssertionError(
                f"commit/rollback found in delivery.py line {lineno}:\n  {line.strip()}"
            )


# ── 3. Filters use currentData() not currentText() for domain values ──────────

def test_filter_combos_use_current_data():
    """_matches_advanced_filters must read filter values via currentData(), not currentText()."""
    src = _source(DELIVERY_UI)
    tree = _ast(DELIVERY_UI)

    # Find the _matches_advanced_filters method body
    method_src = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_matches_advanced_filters":
                lines = src.splitlines()
                method_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

    assert method_src is not None, "_matches_advanced_filters method not found in delivery.py"

    # Must use currentData() for _flt_ combos
    for combo in ("_flt_estado", "_flt_flujo", "_flt_origen"):
        assert f"{combo}.currentData()" in method_src, (
            f"{combo} must use currentData() in _matches_advanced_filters"
        )

    # Must NOT compare against string "Todos" or "Todo" for filter gate
    assert 'currentText()' not in method_src or all(
        'currentData()' in line for line in method_src.splitlines()
        if '_flt_' in line and 'currentText()' in line
    ), "Filter combos must not use currentText() for domain value checks"


# ── 4. Filters check `is not None` not `!= "Todos"` ─────────────────────────

def test_filter_gate_uses_none_not_string():
    """Filter gate must use `is not None` instead of `!= 'Todos'`."""
    src = _source(DELIVERY_UI)
    tree = _ast(DELIVERY_UI)

    method_src = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_matches_advanced_filters":
                lines = src.splitlines()
                method_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

    assert method_src is not None
    for combo in ("_flt_estado", "_flt_flujo", "_flt_origen"):
        # Must not use != "Todos" / != 'Todos' in filter gate
        pattern = re.compile(rf"{re.escape(combo)}.*!=\s*['\"]Todos['\"]")
        assert not pattern.search(method_src), (
            f"{combo} filter gate must use 'is not None', not '!= \"Todos\"'"
        )


# ── 5. ChangeDeliveryStatusUseCase is the only write path ────────────────────

def test_delivery_service_delegates_update_status():
    """delivery_service.update_status must delegate to ChangeDeliveryStatusUseCase."""
    src = _source(DELIVERY_SERVICE)
    assert "ChangeDeliveryStatusUseCase" in src, (
        "delivery_service.py must use ChangeDeliveryStatusUseCase for update_status"
    )


# ── 6. State machine is used inside ChangeDeliveryStatusUseCase ──────────────

def test_state_machine_used_in_change_status_use_case():
    src = _source(CHANGE_STATUS_UC)
    assert "DeliveryStateMachine" in src, (
        "ChangeDeliveryStatusUseCase must use DeliveryStateMachine"
    )


# ── 7. No integer cast on order_id in delivery UI ────────────────────────────

def test_no_int_cast_on_order_id_in_delivery_ui():
    """int(order_id) or int(pedido_id) casts are forbidden per REGLA CERO."""
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\bint\s*\(\s*(order_id|pedido_id)\s*\)", line):
            raise AssertionError(
                f"int() cast on order_id/pedido_id found in delivery.py line {lineno}:\n  {line.strip()}"
            )


# ── 8. assign_driver routes through AssignDeliveryDriverUseCase ──────────────

def test_assign_driver_routes_through_use_case():
    """delivery_service.assign_driver must delegate to AssignDeliveryDriverUseCase."""
    src = _source(DELIVERY_SERVICE)
    assert "AssignDeliveryDriverUseCase" in src, (
        "delivery_service.py must use AssignDeliveryDriverUseCase for assign_driver"
    )
