from __future__ import annotations

import importlib.util
import re
import uuid
from pathlib import Path
from unittest.mock import patch

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
IDS_PATH = PACKAGE_ROOT / "backend" / "shared" / "ids.py"
MONITORED_SUFFIXES = {".py", ".sql"}
IGNORED_PREFIXES = ("docs/", "tests/")

FORBIDDEN_IDENTITY_BASELINE = {
    "INTEGER PRIMARY KEY AUTOINCREMENT": 392,
    "lastrowid": 123,
    "legacy_id": 2,
    "int(product_id)": 30,
    "int(branch_id)": 26,
    "int(sale_id)": 2,
    "int(customer_id)": 1,
    "int(reservation_id)": 3,
}

FORBIDDEN_IDENTITY_PATTERNS = {
    "INTEGER PRIMARY KEY AUTOINCREMENT": re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.IGNORECASE),
    "lastrowid": re.compile(r"lastrowid", re.IGNORECASE),
    "legacy_id": re.compile(r"legacy_id", re.IGNORECASE),
    "int(product_id)": re.compile(r"int\(product_id\)", re.IGNORECASE),
    "int(branch_id)": re.compile(r"int\(branch_id\)", re.IGNORECASE),
    "int(sale_id)": re.compile(r"int\(sale_id\)", re.IGNORECASE),
    "int(customer_id)": re.compile(r"int\(customer_id\)", re.IGNORECASE),
    "int(reservation_id)": re.compile(r"int\(reservation_id\)", re.IGNORECASE),
}


def _iter_monitored_sources():
    for path in PACKAGE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MONITORED_SUFFIXES:
            continue
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        if relative.startswith(IGNORED_PREFIXES):
            continue
        yield path


def _load_ids_module():
    spec = importlib.util.spec_from_file_location("spj_backend_shared_ids", IDS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_uuid_returns_canonical_lowercase_uuidv7_string():
    ids = _load_ids_module()

    generated = ids.new_uuid()
    parsed = uuid.UUID(generated)

    assert generated == str(parsed)
    assert generated == generated.lower()
    assert parsed.version == 7


def test_new_uuid_fallback_returns_uuidv7_when_runtime_lacks_uuid7():
    ids = _load_ids_module()

    with patch.object(ids.uuid, "uuid7", None, create=True):
        generated = ids.new_uuid()

    parsed = uuid.UUID(generated)
    assert generated == str(parsed)
    assert generated == generated.lower()
    assert parsed.version == 7


def test_new_uuid_generates_unique_values_offline():
    ids = _load_ids_module()

    generated = {ids.new_uuid() for _ in range(1000)}

    assert len(generated) == 1000


def test_uuidv7_cutover_forbidden_identity_patterns_do_not_increase():
    counts = {name: 0 for name in FORBIDDEN_IDENTITY_PATTERNS}
    for path in _iter_monitored_sources():
        content = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in FORBIDDEN_IDENTITY_PATTERNS.items():
            counts[name] += len(pattern.findall(content))

    regressions = {
        name: {"baseline": FORBIDDEN_IDENTITY_BASELINE[name], "current": current}
        for name, current in counts.items()
        if current > FORBIDDEN_IDENTITY_BASELINE[name]
    }
    assert not regressions
