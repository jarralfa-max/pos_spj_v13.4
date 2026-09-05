"""ASSET-1 (REGLA CERO, §12, §42, §64, §110) — Activos identity is UUIDv7 only.

No INTEGER PRIMARY KEY / AUTOINCREMENT, no lastrowid or MAX(id)+1 as identity,
no uuid4() and no int(..._id) casts of domain identifiers anywhere under the
Assets/EAM bounded context.
"""

from __future__ import annotations

import re

import pytest

from tests.architecture.assets_guardrails import (
    ASSET_SCHEMA_FILE,
    asset_backend_py_files,
    relative,
)

_AUTOINCREMENT = re.compile(r"AUTOINCREMENT|INTEGER\s+PRIMARY\s+KEY", re.IGNORECASE)
_LASTROWID = re.compile(r"\blastrowid\b|MAX\s*\(\s*id\s*\)\s*\+\s*1")
_INT_ID_CAST = re.compile(r"\bint\s*\(\s*[\w\.]*_id\b")
_UUID4 = re.compile(r"\buuid4\s*\(\s*\)|uuid\.uuid4\s*\(\s*\)")


def _all_files():
    files = list(asset_backend_py_files())
    if ASSET_SCHEMA_FILE.exists():
        files.append(ASSET_SCHEMA_FILE)
    return files


def test_assets_schema_has_no_integer_identity():
    if not ASSET_SCHEMA_FILE.exists():
        pytest.skip("assets_schema.py no existe aún — persistencia llega en una fase posterior")
    text = ASSET_SCHEMA_FILE.read_text(encoding="utf-8")
    assert not _AUTOINCREMENT.search(text), (
        "assets_schema usa identidad entera; debe ser TEXT UUIDv7")


def test_assets_code_has_no_integer_identity_patterns():
    offenders = []
    for path in _all_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _LASTROWID.search(line) or _INT_ID_CAST.search(line) or _AUTOINCREMENT.search(line):
                offenders.append(f"{relative(path)}:{n}: {line.strip()}")
    assert not offenders, (
        "identidad entera / cast int(_id) en Activos (usar UUIDv7 via new_uuid()):\n"
        + "\n".join(offenders)
    )


def test_assets_code_does_not_use_uuid4():
    offenders = []
    for path in _all_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _UUID4.search(line):
                offenders.append(f"{relative(path)}:{n}: {line.strip()}")
    assert not offenders, (
        "uuid4() usado en Activos; la única identidad permitida es UUIDv7 "
        "via backend.shared.ids.new_uuid():\n" + "\n".join(offenders)
    )
