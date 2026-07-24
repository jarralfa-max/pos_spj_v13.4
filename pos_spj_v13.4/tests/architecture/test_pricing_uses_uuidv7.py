"""PRC-9 audit — Pricing/Costing usa UUIDv7 como única identidad (REGLA CERO).

- El esquema `pricing_schema` no declara ninguna PK/columna
  `INTEGER PRIMARY KEY AUTOINCREMENT`; los ids son TEXT.
- El código de dominio/aplicación/repositorio de pricing no usa `lastrowid`,
  `AUTOINCREMENT`, ni casts de identidad `int(<algo>_id)`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.infrastructure.db.schema.pricing_schema import _DDL

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (
    _ROOT / "backend" / "domain" / "pricing",
    _ROOT / "backend" / "application" / "pricing",
    _ROOT / "backend" / "infrastructure" / "db" / "repositories" / "pricing",
)
_INT_ID_CAST = re.compile(r"\bint\(\s*[a-z_]*_id\b", re.IGNORECASE)


def test_schema_has_no_autoincrement():
    joined = "\n".join(_DDL).upper()
    assert "AUTOINCREMENT" not in joined
    assert "INTEGER PRIMARY KEY" not in joined


def test_schema_ids_are_text():
    # cada tabla declara `id TEXT PRIMARY KEY` o PK compuesta TEXT
    joined = "\n".join(_DDL)
    assert "id TEXT PRIMARY KEY" in joined


def test_pricing_code_has_no_lastrowid_or_int_id_casts():
    offenders = []
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "lastrowid" in text:
                offenders.append(f"{path.relative_to(_ROOT)}: lastrowid")
            if "AUTOINCREMENT" in text.upper():
                offenders.append(f"{path.relative_to(_ROOT)}: AUTOINCREMENT")
            for m in _INT_ID_CAST.finditer(text):
                offenders.append(f"{path.relative_to(_ROOT)}: {m.group(0)})")
    assert not offenders, f"Identidad no-UUID en Pricing: {offenders}"
