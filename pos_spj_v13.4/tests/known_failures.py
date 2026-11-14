"""Lectura de ``tests/known_failures.txt`` y clave estable de cada prueba.

La usan ``tests/conftest.py`` (marca las fallas preexistentes como xfail) y
``tests/architecture/test_known_failures_only_shrink.py`` (la lista sólo encoge).
"""
from __future__ import annotations

import re
from pathlib import Path

#: Raíz del paquete (``pos_spj_v13.4/``): los nodeids de la lista son relativos a ella.
PKG_ROOT = Path(__file__).resolve().parents[1]
KNOWN_FAILURES_FILE = Path(__file__).resolve().with_name("known_failures.txt")

_BACKLOG_ITEM = re.compile(r"\bSDLC-[A-Z]+(?:-[A-Z]+)*-\d{3}\b")


def parse_lines(text: str) -> list[tuple[str, str]]:
    """``[(nodeid, ítem)]`` en orden. Ignora líneas vacías y comentarios.

    El ítem es el primer ``SDLC-…`` del comentario de la línea, o ``""`` si no hay.
    """
    entries: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        nodeid, _, comment = line.partition("  #")
        match = _BACKLOG_ITEM.search(comment)
        entries.append((nodeid.strip(), match.group(0) if match else ""))
    return entries


def load(path: Path = KNOWN_FAILURES_FILE) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    return parse_lines(path.read_text(encoding="utf-8"))


def item_key(item) -> str:
    """Nodeid de ``item`` relativo a ``PKG_ROOT`` con ``/``.

    No depende del directorio desde el que se corre pytest ni del sistema operativo.
    """
    path = Path(str(item.path)).resolve()
    try:
        rel = path.relative_to(PKG_ROOT).as_posix()
    except ValueError:
        return item.nodeid
    _, sep, rest = item.nodeid.partition("::")
    return f"{rel}::{rest}" if sep else rel
