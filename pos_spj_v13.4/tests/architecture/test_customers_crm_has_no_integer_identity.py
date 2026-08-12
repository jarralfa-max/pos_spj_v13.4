"""CRM-1 (§11 REGLA CERO) — no integer functional identity in the CRM context.

Forbidden anywhere under the canonical CRM backend roots or its schema file:
``INTEGER PRIMARY KEY``, ``AUTOINCREMENT``, ``lastrowid``, ``MAX(id) + 1``,
``legacy_id``, and the ``int | str`` / ``str | int`` dual-identity contract.
Mirrors ``tests/architecture/test_no_lastrowid_entity_identity.py`` /
``test_no_int_id_casts.py`` but scoped to the new bounded context so it acts
as a hard wall from day one instead of a ratchet over legacy debt.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import (
    CRM_SCHEMA_FILE,
    ALL_CRM_CODE_ROOTS,
    crm_py_files,
    relative,
)

_FORBIDDEN = re.compile(
    r"INTEGER\s+PRIMARY\s+KEY|AUTOINCREMENT|\blastrowid\b|MAX\(\s*id\s*\)\s*\+\s*1"
    r"|\blegacy_id\b|int\s*\|\s*str|str\s*\|\s*int",
    re.IGNORECASE,
)


def _iter_targets():
    for path in crm_py_files(ALL_CRM_CODE_ROOTS):
        yield path
    if CRM_SCHEMA_FILE.exists():
        yield CRM_SCHEMA_FILE


def test_customers_crm_has_no_integer_identity():
    offenders = []
    for path in _iter_targets():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _FORBIDDEN.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {stripped}")
    assert not offenders, (
        "Integer functional identity found in the CRM bounded context "
        "(REGLA CERO requires UUIDv7 TEXT ids only):\n" + "\n".join(offenders)
    )
