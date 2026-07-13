"""Remediación D (T8) — Los QDialog deben ser captura-only.

Contrato objetivo (DEEP_AUDIT_ALL_MODULES §8 / §17):

    Un diálogo SOLO captura datos → DTO/Command. La persistencia
    (``execute``/``commit``), la publicación de eventos (``publish``) y los
    asientos contables (``registrar_asiento``) viven en la capa de servicios;
    el módulo delega en ellos tras ``dialog.exec_()``.

Este guardrail hace AST sobre toda clase que herede de ``QDialog`` en las capas
de presentación (``modulos/``, ``ui/``, ``interfaz/``) y falla si contiene una
llamada prohibida, salvo que la clase esté en ``DIALOG_BUSINESS_LOGIC_ALLOWLIST``.

El allowlist es un RATCHET:
  * No se admiten violaciones nuevas (clase fuera del allowlist).
  * Cuando un diálogo se limpia, su entrada del allowlist DEBE retirarse: el
    test falla si una entrada quedó obsoleta. Así el contador sólo decrece.
"""
from __future__ import annotations

import ast
from pathlib import Path

from tests.architecture.allowlists import DIALOG_BUSINESS_LOGIC_ALLOWLIST

REPO = Path(__file__).resolve().parents[2]
PRESENTATION_DIRS = ("modulos", "ui", "interfaz")

# Llamadas que un diálogo NUNCA debe realizar: transacción, publicación de
# eventos o asiento contable. Estas se prohíben incondicionalmente.
FORBIDDEN_CALLS = frozenset({"commit", "publish", "registrar_asiento"})

# Acceso directo a la DB. Sólo cuenta como violación cuando el PRIMER argumento
# es una cadena SQL (literal o f-string); así NO se marca el patrón legítimo de
# caso de uso `use_case.execute(command)`, que pasa un objeto/comando, no SQL.
SQL_EXEC_CALLS = frozenset({"execute", "executescript", "executemany"})


def _is_qdialog(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name == "QDialog":
            return True
    return False


def _first_arg_is_sql(node: ast.Call) -> bool:
    """True si el primer argumento parece SQL (literal str o f-string)."""
    if not node.args:
        return False
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return True
    if isinstance(arg, ast.JoinedStr):  # f-string
        return True
    # SQL construido con "...".format(...) o "..." % (...)
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) \
            and arg.func.attr == "format" and isinstance(arg.func.value, ast.Constant):
        return True
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod) \
            and isinstance(arg.left, ast.Constant) and isinstance(arg.left.value, str):
        return True
    return False


def _forbidden_hits(cls: ast.ClassDef) -> list[str]:
    hits: set[str] = set()
    for node in ast.walk(cls):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in FORBIDDEN_CALLS:
                hits.add(name)
            elif name in SQL_EXEC_CALLS and _first_arg_is_sql(node):
                hits.add(name)
    return sorted(hits)


def _scan_violators() -> dict[str, list[str]]:
    violators: dict[str, list[str]] = {}
    for rel_dir in PRESENTATION_DIRS:
        base = REPO / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            rel = f"pos_spj_v13.4/{path.relative_to(REPO).as_posix()}"
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and _is_qdialog(node):
                    hits = _forbidden_hits(node)
                    if hits:
                        violators[f"{rel}::{node.name}"] = hits
    return violators


def test_no_new_dialog_business_logic():
    """Ninguna clase QDialog fuera del allowlist puede ejecutar lógica prohibida."""
    violators = _scan_violators()
    nuevos = sorted(set(violators) - set(DIALOG_BUSINESS_LOGIC_ALLOWLIST))
    assert not nuevos, (
        "Diálogos con lógica de negocio no permitida (deben capturar DTO y delegar "
        "en un servicio):\n  " + "\n  ".join(f"{k} -> {violators[k]}" for k in nuevos)
    )


def test_dialog_allowlist_has_no_stale_entries():
    """Ratchet: si un diálogo ya se limpió, su entrada del allowlist debe retirarse."""
    violators = _scan_violators()
    obsoletos = sorted(set(DIALOG_BUSINESS_LOGIC_ALLOWLIST) - set(violators))
    assert not obsoletos, (
        "Entradas obsoletas en DIALOG_BUSINESS_LOGIC_ALLOWLIST (retíralas — el "
        "diálogo ya no viola el contrato):\n  " + "\n  ".join(obsoletos)
    )
