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
    """No *.lastrowid used as domain identity in business code.

    lastrowid is an SQLite INTEGER row ID, not a UUID identity.
    Modules below are explicitly in their own pending migration phase:
    - finance/: full double-entry rewrite pending
    - outbox.py: uses rowid for ordered delivery queue, not entity identity
    - caja_application_service.py, cierre_caja_service.py: cash session rewrite pending
    - cotizacion_service.py, happy_hour_service.py, anticipo_service.py: auxiliary
    - pedido_wa.py, compras_inventariables_engine.py: legacy WA/purchases pending
    """
    violations = []
    pat = re.compile(r'\blastrowid\b')
    _PENDING_MIGRATION = (
        "enterprise/finance_service.py",
        "finance/",
        "rrhh/",
        "outbox.py",
        "caja_application_service.py",
        "cierre_caja_service.py",
        "cotizacion_service.py",
        "happy_hour_service.py",
        "anticipo_service.py",
        "pedido_wa.py",
        "compras_inventariables_engine.py",
        "whatsapp_service.py",
        "reporte_email_service.py",
        "card_batch_engine.py",
        "delivery_outbox_repository.py",
    )
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in _PENDING_MIGRATION):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, ".lastrowid used as identity:\n" + "\n".join(violations)


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
    """No item.get('producto_id') WITHOUT a .get('product_id') fallback in canonical services.

    In NEW canonical code, use 'product_id' only.  Legacy event handlers and
    wiring that bridge both old and new payloads may keep a dual-key pattern
    temporarily — only canonical services are enforced here.
    """
    violations = []
    # Flag .get('producto_id') when it appears WITHOUT product_id on the same line
    # (meaning it is not a dual-key fallback bridge)
    solo_pat = re.compile(r'\.get\(["\']producto_id["\']')
    bridge_pat = re.compile(r'product_id')
    _CANONICAL = (
        "infrastructure/persistence/",
        "core/services/reservation_service.py",
        "core/delivery/application/",
        "backend/application/use_cases/",
    )
    excl = ("migrations", "scripts", "seed")
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in excl):
            continue
        if not any(c in relpath for c in _CANONICAL):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if solo_pat.search(stripped) and not stripped.startswith("#"):
                if not bridge_pat.search(stripped):
                    violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "Sole .get('producto_id') in canonical services:\n" + "\n".join(violations)


def test_no_uuid4_for_entity_ids():
    """uuid.uuid4() must not be used to generate entity IDs; use new_uuid() instead.

    Exception: uuid.uuid4().hex[...] is allowed for savepoint names and folio suffixes
    (they are not entity PKs stored in the DB).  CFDI UUIDs are fiscal, not domain IDs.
    """
    violations = []
    # Match uuid.uuid4() used as a full identity string — NOT followed by .hex or .int
    pat = re.compile(r'\buuid\.uuid4\(\)(?!\.(?:hex|int)\b)')
    excl = ("shared/ids.py", "migrations", "scripts", "cfdi_service.py")
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
    """'Principal' must not be used as a silent branch identity fallback.

    Allowed: SQL COALESCE display aliases, docstrings, log messages, comment lines.
    Forbidden: default values assigned to sucursal_nombre / branch_name fields.
    """
    violations = []
    pat = re.compile(r'["\']Principal["\']')
    # These are structural defaults that assign "Principal" as business identity
    assign_pat = re.compile(r'(?:sucursal_nombre|branch_name)\s*[:=].*["\']Principal["\']|["\']Principal["\'].*as\s+(?:sucursal_nombre|branch_name)')
    excl = ("migrations", "scripts", "seed", "tests", "report_engine")
    for abs_path, relpath in _business_files():
        if any(ex in relpath for ex in excl):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if not pat.search(stripped):
                continue
            if stripped.startswith("#"):
                continue
            # Allow docstrings / log messages / COALESCE SQL
            if stripped.startswith(('"""', "'''", "logger", "COALESCE")):
                continue
            if assign_pat.search(stripped) or "sucursal_nombre" in stripped or "sucursal_nombre" in stripped:
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "'Principal' branch fallback found:\n" + "\n".join(violations)


def test_no_inventario_actual_in_canonical_services():
    """inventario_actual must not be queried in NEW canonical services.

    The legacy table is being phased out. These canonical services must use
    inventory_stock only. Legacy engines (distribution, production, forecast,
    unified inventory) are tracked separately during the migration phase.
    """
    violations = []
    pat = re.compile(r'\binventario_actual\b')
    # Canonical new services that must be inventario_actual-free
    _CANONICAL = (
        "infrastructure/persistence/",
        "core/services/reservation_service.py",
        "core/delivery/",
        "backend/application/use_cases/",
    )
    for abs_path, relpath in _business_files():
        if not any(relpath.startswith(c) or c in relpath for c in _CANONICAL):
            continue
        if "migrations" in relpath:
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "Legacy inventario_actual in canonical services:\n" + "\n".join(violations)
