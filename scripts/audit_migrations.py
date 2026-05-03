#!/usr/bin/env python3
"""
scripts/audit_migrations.py — Auditoría de migraciones SPJ ERP.

Verifica que:
  - Los archivos en migrations/standalone/ son accesibles
  - Las versiones registradas en engine.py están todas presentes

Uso:
    python scripts/audit_migrations.py
"""
from __future__ import annotations
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR   = os.path.dirname(_SCRIPT_DIR)
_PKG_DIR    = os.path.join(_ROOT_DIR, "pos_spj_v13.4")

for _p in [_PKG_DIR, _ROOT_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

_STANDALONE_DIR = os.path.join(_PKG_DIR, "migrations", "standalone")
_ENGINE_PATH    = os.path.join(_PKG_DIR, "migrations", "engine.py")


def scan_standalone() -> dict:
    """
    Retorna {version: filename} de todos los archivos .py en migrations/standalone/
    (excluye __init__ y __pycache__).
    """
    result = {}
    if not os.path.isdir(_STANDALONE_DIR):
        return result
    for fname in os.listdir(_STANDALONE_DIR):
        if not fname.endswith(".py"):
            continue
        if fname.startswith("__"):
            continue
        # Extract numeric version prefix (e.g. "030" from "030_recetas_industriales.py")
        num = fname.split("_")[0]
        result[num] = fname
    return result


def scan_engine() -> dict:
    """
    Retorna {version: module_path} de las migraciones registradas en engine.py MIGRATIONS list.
    """
    result = {}
    try:
        from migrations.engine import MIGRATIONS
        for version, module_path in MIGRATIONS:
            result[version] = module_path
    except Exception:
        # Fallback: parse engine.py as text
        if not os.path.isfile(_ENGINE_PATH):
            return result
        import re
        src = open(_ENGINE_PATH).read()
        for m in re.finditer(r'\("([^"]+)"\s*,\s*"([^"]+)"\)', src):
            result[m.group(1)] = m.group(2)
    return result


def audit() -> list:
    """Run full audit. Returns list of warning strings."""
    standalone = scan_standalone()
    engine     = scan_engine()
    warnings   = []
    for ver in engine:
        if ver.startswith("m"):
            continue
        if ver not in standalone:
            warnings.append(f"MISSING file for engine version {ver}")
    for ver in standalone:
        if ver not in engine:
            warnings.append(f"UNREGISTERED standalone file {standalone[ver]}")
    return warnings


if __name__ == "__main__":
    standalone = scan_standalone()
    engine     = scan_engine()
    print(f"Standalone files: {len(standalone)}")
    print(f"Engine entries:   {len(engine)}")
    issues = audit()
    if issues:
        for w in issues:
            print(f"  WARN {w}")
    else:
        print("  OK All migrations consistent")
