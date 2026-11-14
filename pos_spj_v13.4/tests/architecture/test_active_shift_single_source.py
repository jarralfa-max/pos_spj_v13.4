"""SDLC-ARQ-SHIFT-001: el turno activo tiene UNA fuente.

Antes había una docena de caminos (sólo `OPEN` en el POS, todos los estados
activos en Caja, una caché en el composition_root y tuplas de estados copiadas
a mano en Finanzas, Organización y Actualizaciones). Esta guardia impide que
vuelvan:

(a) sólo `ActiveShiftResolver` busca el turno activo en el repositorio;
(b) nadie guarda el turno activo en `active_cash_shift_id`;
(c) ningún SQL sobre `cash_shifts` filtra el estado con literales fuera del
    repositorio de Caja (los estados salen de `CashShiftLifecyclePolicy`);
(d) ningún archivo que trabaja con turnos copia una tupla/lista/conjunto de
    estados de turno fuera del dominio de Caja.

`migrations/` queda fuera: sus índices `ux_cash_shift_active_*` son la copia
del conjunto en el esquema.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("backend", "frontend")
RESOLVER = "backend/application/cash_register/active_shift_resolver.py"
REPOSITORY = "backend/infrastructure/db/repositories/cash_register/repositories.py"
DOMAIN = "backend/domain/cash_register/"

_SHIFT_STATUSES = frozenset({
    "OPENING", "OPEN", "SUSPENDED", "PENDING_COUNT", "COUNTING", "COUNTED",
    "PENDING_REVIEW", "CLOSING", "CLOSED", "FORCE_CLOSED", "CANCELLED",
})
_ACTIVE = "OPENING|OPEN|SUSPENDED|PENDING_COUNT|COUNTING|COUNTED|PENDING_REVIEW|CLOSING"
# `status` o `s.status`, nunca `c.status` (estado de otra tabla del mismo SQL).
_STATUS = r"(?<![\w.])(?:s\.)?status"
_LITERAL_FILTERS = (
    re.compile(_STATUS + r"\s*(?:NOT\s+)?IN\s*\(\s*'", re.IGNORECASE),
    re.compile(_STATUS + r"\s*(?:=|<>|!=)\s*'(?:" + _ACTIVE + r")'", re.IGNORECASE),
)
_OLD_FINDERS = ("find_open_for_cashier", "find_active_for_cashier", "find_active_for_resource")


def _sources():
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


def _texts(tree: ast.AST):
    """Cada literal de texto, con los f-strings unidos en un solo texto."""
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            yield "".join(part.value for part in node.values
                          if isinstance(part, ast.Constant) and isinstance(part.value, str))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def violations(rel: str, source: str) -> list[str]:
    found: list[str] = []
    tree = ast.parse(source)
    # (a)
    for name in _OLD_FINDERS:
        if name in source:
            found.append(f"{rel}: usa {name} (retirado; usa ActiveShiftResolver)")
    if rel not in (RESOLVER, REPOSITORY):
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "find_active"):
                found.append(f"{rel}:{node.lineno}: find_active fuera de ActiveShiftResolver")
    # (b)
    if "active_cash_shift_id" in source:
        found.append(f"{rel}: caché active_cash_shift_id (el turno se lee de la base)")
    # (c)
    if rel != REPOSITORY:
        for text in _texts(tree):
            if "cash_shifts" not in text:
                continue
            for pattern in _LITERAL_FILTERS:
                match = pattern.search(text)
                if match:
                    found.append(f"{rel}: SQL de cash_shifts con estados literales: {match.group(0)!r}")
    # (d)
    if not rel.startswith(DOMAIN) and "cash_shift" in source.lower():
        for node in ast.walk(tree):
            if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                values = {element.value for element in node.elts
                          if isinstance(element, ast.Constant) and isinstance(element.value, str)}
                if len(values & _SHIFT_STATUSES) >= 2:
                    found.append(f"{rel}:{node.lineno}: estados de turno copiados {sorted(values)}")
    return found


def test_active_shift_has_a_single_source():
    found = [item for rel, source in _sources() for item in violations(rel, source)]
    assert not found, "\n".join(found)


def test_the_guard_detects_each_kind_of_violation():
    planted = {
        "a": "def f(uow):\n    return uow.shifts.find_open_for_cashier(branch_id=1)\n",
        "a2": "def f(repo):\n    return repo.find_active(cashier_user_id='x')\n",
        "b": "def f(root):\n    setattr(root, 'active_cash_shift_id', 'x')\n",
        "c": "SQL = \"SELECT * FROM cash_shifts WHERE status IN ('OPEN','SUSPENDED')\"\n",
        "c2": "SQL = f\"SELECT {x} FROM cash_shifts s WHERE s.status='OPEN'\"\n",
        "d": "# cash_shifts\nSTATES = ('OPEN', 'SUSPENDED', 'CLOSING')\n",
    }
    for key, source in planted.items():
        assert violations("backend/application/elsewhere.py", source), key


def test_the_guard_allows_legitimate_uses():
    allowed = (
        # El estado de OTRA tabla en un SQL que también lee cash_shifts.
        "SQL = \"SELECT 1 FROM cash_counts c JOIN cash_shifts s ON s.id=c.shift_id"
        " WHERE c.status='OPEN'\"\n",
        # Orden de presentación, no un filtro.
        "SQL = \"SELECT * FROM cash_shifts s ORDER BY CASE s.status WHEN 'OPEN' THEN 0 END\"\n",
        # Placeholders desde la política.
        "SQL = f\"SELECT * FROM cash_shifts WHERE status IN ({marks})\"\n",
    )
    for source in allowed:
        assert not violations("backend/application/elsewhere.py", source), source
