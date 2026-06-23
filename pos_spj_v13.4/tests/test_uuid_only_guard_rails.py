"""Guard rail tests: fail if any prohibited legacy integer-identity pattern exists in business code."""
from __future__ import annotations

import os
import re

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_BUSINESS_DIRS = ("backend", "core", "application", "domain")

_EXCLUDED_SUFFIXES = (
    "tests/test_uuid_only_guard_rails.py",
)

_EXCLUDED_FRAGMENTS = (".venv", ".git", "__pycache__", "migrations/m000_base_schema.py")


def _is_excluded(relpath: str) -> bool:
    for ex in _EXCLUDED_SUFFIXES:
        if relpath.endswith(ex):
            return True
    for frag in _EXCLUDED_FRAGMENTS:
        if frag in relpath:
            return True
    return False


def _business_files():
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith(".py"):
                continue
            abs_path = os.path.join(dirpath, f)
            relpath = os.path.relpath(abs_path, ROOT)
            if _is_excluded(relpath):
                continue
            if any(relpath.startswith(d + os.sep) or relpath.startswith(d + "/") for d in _BUSINESS_DIRS):
                yield abs_path, relpath


def test_no_integer_id_casts_on_entity_ids():
    """No int() casts on entity IDs in business code."""
    violations = []
    pat = re.compile(
        r'\bint\s*\(\s*(?:product|branch|sale|customer|pedido|cliente|sucursal|proveedor|delivery|venta|order)_id\b'
    )
    for abs_path, relpath in _business_files():
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            if pat.search(line):
                violations.append(f"{relpath}:{lineno}: {line.strip()}")
    assert not violations, "int() casts on entity IDs found:\n" + "\n".join(violations)


def test_no_legacy_maps():
    """No LEGACY_*_MAP constants in business code."""
    violations = []
    pat = re.compile(r'\bLEGACY_(?:UNIT|STATUS|PAYMENT|FULFILLMENT)_MAP\b')
    for abs_path, relpath in _business_files():
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            if pat.search(line):
                violations.append(f"{relpath}:{lineno}: {line.strip()}")
    assert not violations, "Legacy maps found:\n" + "\n".join(violations)


def test_no_lastrowid_as_identity():
    """No cursor.lastrowid as domain identity in business code."""
    violations = []
    pat = re.compile(r'cursor\.lastrowid')
    for abs_path, relpath in _business_files():
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            if pat.search(line):
                violations.append(f"{relpath}:{lineno}: {line.strip()}")
    assert not violations, "cursor.lastrowid found in:\n" + "\n".join(violations)


def test_no_legacy_id_fields():
    """No legacy_id or legacy_product_id as code identifiers in business code.

    String literals in log messages are allowed — they're labels, not code.
    """
    violations = []
    pat = re.compile(r'\blegacy_(?:product_)?id\b')
    # Matches only outside string literals: look for assignments, function args, class fields
    code_pat = re.compile(r'(?:self\.|cls\.)?legacy_(?:product_)?id\s*[=:(,]')
    for abs_path, relpath in _business_files():
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and code_pat.search(stripped):
                # Skip pure string literals (log messages, docstrings)
                if not re.match(r'^\s*["\']', stripped) and not stripped.startswith("logger"):
                    violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "legacy_id code identifiers found:\n" + "\n".join(violations)


def test_no_dual_where_clauses():
    """No dual WHERE product_id = ? OR legacy_id = ? patterns."""
    violations = []
    pat = re.compile(r'(?:product_id|branch_id)\s*=\s*\?\s*OR\s*legacy_')
    for abs_path, relpath in _business_files():
        src = open(abs_path).read()
        if pat.search(src):
            violations.append(relpath)
    assert not violations, "Dual legacy WHERE clauses found in:\n" + "\n".join(violations)


def test_no_producto_id_as_item_identity():
    """No item.get('producto_id') or payload.get('producto_id') as entity identity.

    'producto_id' is the legacy Spanish key; canonical key is 'product_id'.
    Only string-literal imports/docstrings and migration files are excluded.
    """
    violations = []
    pat = re.compile(r'\.get\(["\']producto_id["\']')
    excl = ("migrations", "scripts", "seed")
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in excl):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "Legacy .get('producto_id') found:\n" + "\n".join(violations)


def test_no_uuid4_for_entity_ids():
    """uuid.uuid4() must not be used to generate entity IDs; use new_uuid() instead."""
    violations = []
    pat = re.compile(r'\buuid\.uuid4\(\)')
    # new_uuid() is the canonical generator; uuid4 is forbidden for entity IDs
    excl = ("shared/ids.py", "migrations", "scripts")
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in excl):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "uuid.uuid4() used for entity IDs:\n" + "\n".join(violations)


def test_no_principal_as_branch_fallback():
    """'Principal' must not be used as a silent branch identity fallback."""
    violations = []
    pat = re.compile(r'["\']Principal["\']')
    excl = ("migrations", "scripts", "seed", "tests")
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in excl):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "'Principal' branch fallback found:\n" + "\n".join(violations)


def test_no_inventario_actual_in_business_code():
    """inventario_actual (legacy table) must not be queried in business code.

    Only migrations are allowed to reference it (for historical drop/rename).
    """
    violations = []
    pat = re.compile(r'\binventario_actual\b')
    for abs_path, relpath in _business_files():
        if "migrations" in relpath:
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "Legacy inventario_actual table referenced:\n" + "\n".join(violations)
