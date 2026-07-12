"""REGLA CERO: prohibido lastrowid como identidad de dominio.

La identidad canónica es UUIDv7 generado con backend.shared.ids.new_uuid().
lastrowid es un rowid entero de SQLite y no puede identificar entidades.
"""

from __future__ import annotations

import re

from .architecture_guardrails import (
    APP_ROOT,
    assert_no_new_violations,
    collect_regex_violations,
    outside_migrations,
)

LASTROWID_RE = re.compile(r"\blastrowid\b")

# Deuda funcional saldada. Las entradas restantes son menciones en
# docstrings/documentación embebida (no código ejecutable).
LASTROWID_ALLOWLIST = {
    "pos_spj_v13.4/scripts/seed_demo.py": 1,
    "pos_spj_v13.4/tools/refactor_control/bootstrap_refactor_state.py": 2,
}


def test_no_lastrowid_entity_identity() -> None:
    violations = collect_regex_violations(
        pattern=LASTROWID_RE,
        roots=(APP_ROOT,),
        path_filter=outside_migrations,
    )
    assert_no_new_violations("lastrowid identity", violations, LASTROWID_ALLOWLIST)


def test_no_lastrowid_in_core_services() -> None:
    """Los servicios canónicos (core/, application/, backend/) están limpios."""
    roots = (
        APP_ROOT / "core",
        APP_ROOT / "application",
        APP_ROOT / "backend",
        APP_ROOT / "repositories",
    )
    violations = collect_regex_violations(pattern=LASTROWID_RE, roots=roots)
    assert not violations, (
        "lastrowid en servicios canónicos:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )
