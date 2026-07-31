"""Procurement desktop composition may wire dependencies, never execute DDL."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "frontend" / "desktop" / "modules" / "purchasing"


def test_procurement_routes_do_not_import_or_create_schema():
    violations = []
    for path in ROUTES.glob("*_routes.py"):
        source = path.read_text(encoding="utf-8")
        if "create_procurement_schema" in source or "infrastructure.db.schema" in source:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"DDL/schema bootstrap en rutas UI: {violations}"


def test_procurement_routes_use_canonical_container_session():
    for name in ("direct_purchase_routes.py", "enterprise_routes.py"):
        source = (ROUTES / name).read_text(encoding="utf-8")
        assert 'getattr(container, "session", None)' in source
        assert "session_context\", None" not in source
