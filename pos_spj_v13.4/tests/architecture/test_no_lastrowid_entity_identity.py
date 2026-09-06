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

# Deuda funcional saldada: CERO. Las tres entradas que este allowlist toleraba
# (seed_demo.py, bootstrap_refactor_state.py x2) eran menciones en docstrings y
# documentación embebida, no código — el propio comentario lo admitía. Con el
# escaneo `code_only` esas menciones ya no se detectan y el allowlist queda vacío,
# que es la dirección legítima del ratchet.
LASTROWID_ALLOWLIST: dict[str, int] = {}


def test_no_lastrowid_entity_identity() -> None:
    violations = collect_regex_violations(
        pattern=LASTROWID_RE,
        roots=(APP_ROOT,),
        path_filter=outside_migrations,
        code_only=True,
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
    violations = collect_regex_violations(pattern=LASTROWID_RE, roots=roots, code_only=True)
    assert not violations, (
        "lastrowid en servicios canónicos:\n"
        + "\n".join(f"{v.relative_path}:{v.line_number}: {v.text}" for v in violations)
    )


def test_code_only_scan_still_catches_executable_lastrowid(tmp_path) -> None:
    """Ignorar docstrings no puede convertir este guard en un no-op."""
    prose = tmp_path / "prose.py"
    prose.write_text('"""Aqui no se usa lastrowid."""\n', encoding="utf-8")
    real = tmp_path / "real.py"
    real.write_text("def save(cur):\n    return cur.lastrowid\n", encoding="utf-8")

    found = collect_regex_violations(pattern=LASTROWID_RE, roots=(tmp_path,), code_only=True)
    flagged = {violation.path.name for violation in found}
    assert "real.py" in flagged, "el guard dejo de detectar lastrowid ejecutable"
    assert "prose.py" not in flagged, "el guard sigue reportando prosa"

