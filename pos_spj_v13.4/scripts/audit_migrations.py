"""
audit_migrations.py — pos_spj v13.4
Detecta duplicados en migrations/standalone/ y verifica coherencia con engine.py.

Uso:
    python scripts/audit_migrations.py
    python scripts/audit_migrations.py --verbose
"""
import os
import re
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
STANDALONE_DIR = ROOT / "pos_spj_v13.4" / "migrations" / "standalone"
ENGINE_FILE = ROOT / "pos_spj_v13.4" / "migrations" / "engine.py"


def scan_standalone():
    """Devuelve dict {numero: [archivos]} para migrations/standalone/."""
    nums = {}
    for f in sorted(STANDALONE_DIR.iterdir()):
        if not f.name.endswith(".py") or f.name.startswith("_"):
            continue
        m = re.match(r"^(\d+)_", f.name)
        if m:
            n = m.group(1)
            nums.setdefault(n, []).append(f.name)
    return nums


def scan_engine():
    """Extrae los números registrados en engine.py."""
    if not ENGINE_FILE.exists():
        return set()
    content = ENGINE_FILE.read_text()
    return set(re.findall(r'"(\d{3})"', content))


def main():
    parser = argparse.ArgumentParser(description="Audita migraciones del proyecto")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    nums = scan_standalone()
    engine_nums = scan_engine()

    duplicates = {n: fs for n, fs in nums.items() if len(fs) > 1}
    in_standalone = set(nums.keys())
    not_in_engine = in_standalone - engine_nums
    not_in_standalone = engine_nums - in_standalone

    ok = True

    print(f"=== AUDITORÍA DE MIGRACIONES — pos_spj v13.4 ===\n")
    print(f"  Directorio: {STANDALONE_DIR}")
    print(f"  Engine:     {ENGINE_FILE}")
    print(f"  Total en standalone: {len(in_standalone)} números únicos")
    print(f"  Total en engine.py:  {len(engine_nums)}\n")

    if duplicates:
        ok = False
        print(f"[CRÍTICO] DUPLICADOS ({len(duplicates)}):")
        for n, files in sorted(duplicates.items()):
            print(f"  [{n}]")
            for f in files:
                path = STANDALONE_DIR / f
                size = path.stat().st_size
                lines = len(path.read_text().splitlines())
                has_run = "run(" in path.read_text() or "crear_tablas(" in path.read_text()
                status = "activo" if has_run else "solo comentario"
                print(f"    {f} ({lines} líneas, {size}B) — {status}")
    else:
        print("[OK] Sin duplicados en standalone/")

    if not_in_engine:
        print(f"\n[AVISO] En standalone pero NO en engine.py ({len(not_in_engine)}):")
        for n in sorted(not_in_engine):
            files = nums[n]
            for f in files:
                path = STANDALONE_DIR / f
                has_run = "run(" in path.read_text() or "crear_tablas(" in path.read_text()
                tag = "⚠ tiene run()" if has_run else "(solo comentario)"
                print(f"  {n}: {f} {tag}")

    if not_in_standalone:
        ok = False
        print(f"\n[CRÍTICO] En engine.py pero NO en standalone ({len(not_in_standalone)}):")
        for n in sorted(not_in_standalone):
            print(f"  {n}: archivo faltante")

    if args.verbose:
        print(f"\n=== ORDEN CANÓNICO ===")
        for n, files in sorted(nums.items()):
            in_eng = "✓ engine" if n in engine_nums else "  -----"
            dup = " ⚠ DUPLICADO" if len(files) > 1 else ""
            print(f"  {n}: {in_eng}{dup} — {files[0]}")

    print(f"\n{'[OK] Auditoría sin problemas críticos' if ok else '[FALLO] Se encontraron problemas críticos'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
