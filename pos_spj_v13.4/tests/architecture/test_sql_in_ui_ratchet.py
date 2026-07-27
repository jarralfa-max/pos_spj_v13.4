"""Remediación F (T13) — Ratchet decreciente de SQL en UI.

`test_no_sql_in_frontend` sólo impide AUMENTOS (actual <= allowed). Este test
cierra el ratchet: exige IGUALDAD exacta entre el conteo real de SQL en la UI y
el contador del allowlist, de modo que:

  · agregar SQL en un archivo de UI → actual > allowed → falla (no regresar);
  · remover SQL → actual < allowed → falla pidiendo BAJAR el contador (el
    allowlist siempre refleja la realidad y sólo puede decrecer);
  · un archivo de UI con SQL que no esté en el allowlist → falla.

El objetivo terminal de cada contador es 0 (SQL fuera de la UI, en repos/servicios).
"""
from __future__ import annotations

from collections import Counter

from .allowlists import SQL_IN_UI_ALLOWLIST
from .architecture_guardrails import SQL_RE, UI_ROOTS, collect_regex_violations


def _actual_counts() -> Counter:
    counts: Counter = Counter()
    for v in collect_regex_violations(pattern=SQL_RE, roots=UI_ROOTS):
        counts[v.relative_path] += 1
    return counts


def test_sql_in_ui_allowlist_is_tight():
    actual = _actual_counts()
    allow = SQL_IN_UI_ALLOWLIST

    # 1) Ningún archivo con SQL puede faltar del allowlist ni exceder su contador.
    increased = {
        path: (cnt, allow.get(path, 0))
        for path, cnt in actual.items()
        if cnt > allow.get(path, 0)
    }
    assert not increased, (
        "SQL en UI AUMENTÓ o apareció en archivo no listado "
        "(mover a repositorio/servicio):\n  "
        + "\n  ".join(f"{p}: actual {c} > allowed {a}" for p, (c, a) in sorted(increased.items()))
    )

    # 2) Ratchet: si un archivo tiene MENOS SQL que su contador, baja el contador.
    loosened = {
        path: (actual.get(path, 0), allowed)
        for path, allowed in allow.items()
        if actual.get(path, 0) < allowed
    }
    assert not loosened, (
        "Contadores de SQL_IN_UI_ALLOWLIST más altos que la realidad — BÁJALOS "
        "(el ratchet sólo decrece):\n  "
        + "\n  ".join(f"{p}: allowed {a} -> actual {c}" for p, (c, a) in sorted(loosened.items()))
    )

    # 3) Entradas con actual 0 deben retirarse del allowlist.
    stale = sorted(p for p in allow if actual.get(p, 0) == 0)
    assert not stale, (
        "Entradas obsoletas en SQL_IN_UI_ALLOWLIST (0 SQL real — retíralas):\n  "
        + "\n  ".join(stale)
    )
