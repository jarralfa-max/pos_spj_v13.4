"""REGLA CERO: prohibido convertir identidades de dominio con int(..._id).

UUIDv7 es la única identidad persistente. Cualquier cast int() sobre un
identificador funcional (producto, venta, sucursal, cliente, usuario, rol,
lote, compra, reserva…) rompe RBAC y los contratos UUID.
"""

from __future__ import annotations

import re

from .architecture_guardrails import (
    APP_ROOT,
    assert_no_new_violations,
    collect_regex_violations,
    outside_migrations,
)

INT_ID_CAST_RE = re.compile(r"\bint\(\s*(?:\w+\.)?\w*_(?:id|row_id)\s*\)")

# Deuda saldada: cero casts int(..._id) permitidos.
INT_ID_CASTS_ALLOWLIST: dict[str, int] = {}


def test_no_int_id_casts() -> None:
    violations = collect_regex_violations(
        pattern=INT_ID_CAST_RE,
        roots=(APP_ROOT,),
        path_filter=outside_migrations,
    )
    assert_no_new_violations("int(..._id) cast", violations, INT_ID_CASTS_ALLOWLIST)


def test_no_int_id_casts_in_permissions_and_session() -> None:
    """RBAC y sesión no toleran NINGÚN cast entero de identidad."""
    critical = (
        APP_ROOT / "repositories" / "config_repository.py",
        APP_ROOT / "core" / "session_context.py",
        APP_ROOT / "security",
        APP_ROOT / "repositories" / "security_repository.py",
    )
    violations = collect_regex_violations(pattern=INT_ID_CAST_RE, roots=critical)
    assert not violations, (
        "Casts int(..._id) en RBAC/sesión:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )
