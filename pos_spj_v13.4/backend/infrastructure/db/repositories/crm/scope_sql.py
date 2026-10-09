"""Traduce un ``CRMDataScope`` a un filtro SQL parametrizado (CRM-43).

Una sola regla para prospectos, oportunidades y casos — la misma que
``CRMDataScope.includes()`` aplica a un registro ya cargado:

* COMPANY  → sin filtro.
* BRANCH   → ``<branch_col> IN (...)``.
* OWN/TEAM → el responsable está entre los miembros, o el registro no tiene
  responsable y lo creó uno de ellos.
"""

from __future__ import annotations


def scope_where(scope, *, responsible_col: str, creator_col: str,
                branch_col: str) -> tuple[str, tuple]:
    if scope.axis == "COMPANY":
        return "1=1", ()
    if scope.axis == "BRANCH":
        branches = tuple(scope.branch_ids)
        if not branches:
            return "1=0", ()
        marks = ",".join("?" for _ in branches)
        return f"{branch_col} IN ({marks})", branches
    members = ((scope.owner_user_id,) if scope.axis == "OWN" else tuple(scope.team_member_ids))
    members = tuple(m for m in members if m)
    if not members:
        return "1=0", ()
    marks = ",".join("?" for _ in members)
    return (f"({responsible_col} IN ({marks}) OR ({responsible_col} IS NULL"
            f" AND {creator_col} IN ({marks})))", members + members)
