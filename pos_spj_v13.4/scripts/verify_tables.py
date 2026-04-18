"""
Wrapper CLI para mantener compatibilidad con `python scripts/verify_tables.py`.

Implementación canónica:
    pos_spj_v13.4/scripts/verify_tables.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_inner_main():
    repo_root = Path(__file__).resolve().parents[1]
    inner_script = repo_root / "pos_spj_v13.4" / "scripts" / "verify_tables.py"
    if not inner_script.exists():
        raise FileNotFoundError(f"No existe script interno: {inner_script}")

    spec = importlib.util.spec_from_file_location("spj_inner_verify_tables", inner_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar spec de {inner_script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


def main() -> int:
    inner_main = _load_inner_main()
    try:
        result = inner_main()
        return int(result or 0)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        return int(code)


if __name__ == "__main__":
    sys.exit(main())
