"""Architecture tests for the Delivery module.

These tests act as guard-rails: they FAIL if someone reintroduces
duplicate routes, direct SQL in UI, or transactions in UI.

Tests 1-5 from the refactor spec (architecture enforcement).
Tests 6-8 from the original file are preserved below.
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


# ══════════════════════════════════════════════════════════════════════════════
# REFACTOR SPEC TESTS (1-5)
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. No raw SQL in modulos/delivery.py ─────────────────────────────────────

_SQL_KEYWORDS = re.compile(
    r'\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|DROP\s+TABLE|CREATE\s+TABLE)\b',
    re.IGNORECASE,
)

def test_no_raw_sql_in_delivery_ui():
    """Test 1: modulos/delivery.py must contain no raw SQL statements."""
    src = _source(DELIVERY_UI)
    violations = []
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if _SQL_KEYWORDS.search(line):
            violations.append(f"  Line {lineno}: {line.rstrip()}")
    assert not violations, (
        "Raw SQL found in modulos/delivery.py:\n" + "\n".join(violations[:10])
    )


# ── 2. No f"... kg" hardcoded pattern ────────────────────────────────────────

def test_no_fstring_kg_in_delivery_ui():
    """Test 2: No f-string with hardcoded 'kg' in delivery module."""
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r'f["\'].*\bkg\b.*["\']', line):
            raise AssertionError(
                f'Hardcoded "kg" in f-string at delivery.py line {lineno}:\n  {line.strip()}'
            )


# ── 3. No bare "kg" string literal in delivery UI ────────────────────────────

def test_no_kg_string_literal_in_delivery_ui():
    """Test 3: 'kg' must not appear as a bare string literal in modulos/delivery.py.

    It may only come through UnitCode enum / UNIT_LABELS_ES.
    Exception: inside comments (allowed for documentation).
    """
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Match quoted "kg" or 'kg' as standalone string literals
        if re.search(r"""["']\s*kg\s*["']""", line):
            raise AssertionError(
                f'Bare "kg" string literal found in delivery.py line {lineno}:\n  {line.strip()}\n'
                'Use UnitCode.KILOGRAM / UNIT_LABELS_ES instead.'
            )


# ── 4. No separate action maps in Kanban vs List ─────────────────────────────

_ACTION_MAP_PATTERN = re.compile(
    r'\b(ACTION_MAP|ACCION_MAP|_actions_map|_action_map|KANBAN_ACTIONS|LIST_ACTIONS)\s*=\s*\{',
    re.IGNORECASE,
)

def test_no_duplicate_action_maps_in_delivery_ui():
    """Test 4: Kanban and list views must not define separate action dicts.

    All actions come from DeliveryActionPolicy (or DeliveryActionDispatcher).
    """
    src = _source(DELIVERY_UI)
    matches = []
    for lineno, line in enumerate(src.splitlines(), 1):
        if _ACTION_MAP_PATTERN.search(line):
            matches.append(f"Line {lineno}: {line.strip()}")
    assert not matches, (
        "Separate action maps found in delivery.py — use DeliveryActionPolicy:\n"
        + "\n".join(matches)
    )


# ── 5. No commit() or rollback() in delivery UI ──────────────────────────────

def test_no_commit_rollback_in_delivery_ui():
    """Test 5: The UI layer must never call commit() or rollback()."""
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r'\.(commit|rollback)\s*\(', line):
            raise AssertionError(
                f"commit/rollback found in delivery.py line {lineno}:\n  {line.strip()}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# ORIGINAL GUARD-RAIL TESTS (preserved)
# ══════════════════════════════════════════════════════════════════════════════

# ── 6. No direct estado UPDATE in UI ─────────────────────────────────────────

def test_no_direct_estado_update_in_delivery_ui():
    """delivery.py must not run UPDATE delivery_orders SET estado= directly."""
    src = _source(DELIVERY_UI)
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.search(r"UPDATE\s+delivery_orders\s+SET\s+estado", line, re.IGNORECASE):
            raise AssertionError(
                f"Direct estado UPDATE found in delivery.py line {lineno}:\n  {line.strip()}"
            )


# ── 7. Filters use currentData() not currentText() ───────────────────────────

def test_filter_combos_use_current_data():
    """_matches_advanced_filters must read filter values via currentData(), not currentText()."""
    src = _source(DELIVERY_UI)
    tree = _ast(DELIVERY_UI)

    method_src = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_matches_advanced_filters":
                lines = src.splitlines()
                method_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                break

    assert method_src is not None, "_matches_advanced_filters method not found in delivery.py"

    for combo in ("_flt_estado", "_flt_flujo", "_flt_origen"):
        assert f"{combo}.currentData()" in method_src, (
            f"{combo} must use currentData() in _matches_advanced_filters"
        )


# ── 8. Filters check `is not None` not `!= "Todos"` ─────────────────────────

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
        pattern = re.compile(rf"{re.escape(combo)}.*!=\s*['\"]Todos['\"]")
        assert not pattern.search(method_src), (
            f"{combo} filter gate must use 'is not None', not '!= \"Todos\"'"
        )


# ── 9. ChangeDeliveryStatusUseCase is the only write path ────────────────────

def test_delivery_service_delegates_update_status():
    """delivery_service.update_status must delegate to ChangeDeliveryStatusUseCase."""
    src = _source(DELIVERY_SERVICE)
    assert "ChangeDeliveryStatusUseCase" in src, (
        "delivery_service.py must use ChangeDeliveryStatusUseCase for update_status"
    )


# ── 10. State machine is used inside ChangeDeliveryStatusUseCase ─────────────

def test_state_machine_used_in_change_status_use_case():
    src = _source(CHANGE_STATUS_UC)
    assert "DeliveryStateMachine" in src, (
        "ChangeDeliveryStatusUseCase must use DeliveryStateMachine"
    )


# ── 11. No integer cast on order_id in delivery UI ───────────────────────────

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


# ── 12. assign_driver routes through AssignDeliveryDriverUseCase ─────────────

def test_assign_driver_routes_through_use_case():
    """delivery_service.assign_driver must delegate to AssignDeliveryDriverUseCase."""
    src = _source(DELIVERY_SERVICE)
    assert "AssignDeliveryDriverUseCase" in src, (
        "delivery_service.py must use AssignDeliveryDriverUseCase for assign_driver"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE CANONICAL READ ROUTE (board orders) — DeliveryQueryService only
# ══════════════════════════════════════════════════════════════════════════════

def test_board_read_uses_query_service_not_repository_route():
    """The board must read orders through DeliveryQueryService, never through
    the legacy delivery_service.list_orders repository route (single source)."""
    src = _source(DELIVERY_UI)
    assert "delivery_service.list_orders" not in src, (
        "modulos/delivery.py still reads orders via delivery_service.list_orders — "
        "the board must use DeliveryQueryService (single canonical read route)."
    )


def test_board_uses_single_shared_visual_state():
    """cargar_pedidos must populate the shared _current_orders DTO collection."""
    src = _source(DELIVERY_UI)
    assert "self._current_orders" in src, (
        "Board must keep a single shared visual state (_current_orders) of DTOs."
    )


def test_board_uses_single_dto_to_view_mapper():
    """Both presentations must project the DTO through the one canonical mapper."""
    src = _source(DELIVERY_UI)
    assert "_dto_to_view_fn" in src, (
        "Board must map DTOs through the single dto_to_view mapper."
    )
