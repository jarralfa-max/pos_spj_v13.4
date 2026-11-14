"""`tests/known_failures.txt` sólo puede encogerse respecto a la rama base.

`tests/conftest.py` marca como xfail cada prueba de esa lista, así que agregar
una línea tapa una falla. Este guardia compara el conjunto de nodeids con el de la
versión de la rama base, en el punto donde la rama actual se separó (merge-base)
o, si la historia es superficial, en la punta de la base. Si aparece un nodeid
que no estaba, falla. Lo único permitido es borrar líneas.

La rama base se toma de `SPJ_BASE_REF`, de `GITHUB_BASE_REF` (en un PR) o, si no
hay ninguna, de la línea «**Rama base:**» de `docs/sdlc/README.md`. En CI la
rama base tiene que estar traída (`ci-segmented.yml` hace el `git fetch`). Si no
se encuentra, en CI la prueba falla y en local se salta.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.known_failures import KNOWN_FAILURES_FILE, PKG_ROOT, load, parse_lines

README = PKG_ROOT / "docs" / "sdlc" / "README.md"


def _base_branch() -> str:
    for var in ("SPJ_BASE_REF", "GITHUB_BASE_REF"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    match = re.search(r"\*\*Rama base:\*\*\s*`([^`]+)`",
                      README.read_text(encoding="utf-8"))
    assert match, "docs/sdlc/README.md no declara la «Rama base»"
    return match.group(1)


def _git(*args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", "-C", str(PKG_ROOT), *args],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 127, ""
    return done.returncode, done.stdout


def _unavailable(reason: str):
    if os.environ.get("CI"):
        pytest.fail(reason + " — en CI la rama base debe traerse antes (git fetch)")
    pytest.skip(reason)


def _base_version() -> tuple[str, str | None]:
    """``(commit comparado, texto de la lista en la base o None si no existía)``."""
    branch = _base_branch()
    ref = next((c for c in (f"origin/{branch}", branch)
                if _git("rev-parse", "--verify", "--quiet", f"{c}^{{commit}}")[0] == 0),
               None)
    if ref is None:
        _unavailable(f"no se encuentra la rama base {branch!r}")
    rc, merge_base = _git("merge-base", "HEAD", ref)
    point = merge_base.strip() if rc == 0 and merge_base.strip() else ref
    rc, top = _git("rev-parse", "--show-toplevel")
    if rc != 0:
        _unavailable("no es un repositorio git")
    rel = KNOWN_FAILURES_FILE.resolve().relative_to(Path(top.strip()).resolve()).as_posix()
    rc, text = _git("show", f"{point}:{rel}")
    return point, (text if rc == 0 else None)


def test_known_failures_entries_are_well_formed():
    entries = load()
    nodeids = [nodeid for nodeid, _ in entries]
    duplicates = sorted({n for n in nodeids if nodeids.count(n) > 1})
    assert not duplicates, f"nodeids repetidos en known_failures.txt: {duplicates}"
    sin_item = [n for n, ref in entries if not ref]
    assert not sin_item, f"cada línea debe nombrar el ítem SDLC-… que la arreglará: {sin_item}"
    sin_prueba = [n for n in nodeids if "::" not in n]
    assert not sin_prueba, f"cada línea debe ser el nodeid de una prueba, no un archivo: {sin_prueba}"
    sin_archivo = sorted({n.split("::", 1)[0] for n in nodeids
                          if not (PKG_ROOT / n.split("::", 1)[0]).is_file()})
    assert not sin_archivo, (
        f"archivos de prueba que ya no existen (borra sus líneas): {sin_archivo}")


def test_known_failures_only_shrink():
    point, base_text = _base_version()
    if base_text is None:
        return  # la base todavía no tiene la lista: es el commit que la introduce
    base = {nodeid for nodeid, _ in parse_lines(base_text)}
    nuevas = sorted({nodeid for nodeid, _ in load()} - base)
    assert not nuevas, (
        f"known_failures.txt sólo puede encogerse; respecto a {point[:12]} se "
        f"agregaron {len(nuevas)} fallas. Arregla la regresión en lugar de "
        "listarla:\n  " + "\n  ".join(nuevas))
