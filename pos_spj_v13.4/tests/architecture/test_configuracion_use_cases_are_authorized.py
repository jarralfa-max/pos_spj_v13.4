"""SDLC-ARQ-PERM-001 — guardia: ningún caso de uso de escritura de
Configuración se construye sin autorizador ni se ejecuta sin `require()`.

Hasta este ítem la única verificación era `ConfiguracionPresenter._authorize`;
cualquier llamador que no pasara por la pantalla escribía sin permiso. Mismo
espíritu que `test_meat_processing_use_cases_are_authorized.py`, pero por AST
(por clase y por método, no contando apariciones en el archivo).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USE_CASES_DIR = ROOT / "backend/application/use_cases/configuracion"
EXTRA_USE_CASES = [ROOT / "backend/application/use_cases/set_installation_branch_use_case.py"]
TICKET_DESIGNER = USE_CASES_DIR / "ticket_designer_service.py"
ROUTES = ROOT / "frontend/desktop/modules/configuracion/configuracion_routes.py"

#: Clases con `execute` que no escriben nada (justificar cada una).
NOT_WRITES = {
    "PreviewLogoUseCase",  # vista previa en un directorio temporal; no persiste
}
#: Métodos de TicketDesignerService que escriben (BD, archivos o impresora).
TICKET_DESIGNER_WRITES = {"print_test", "import_logo", "set_company_logo", "set_branch_logo"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _calls_require(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in ("require", "require_mapped")
               for n in ast.walk(node))


def _first_statement_requires(fn: ast.FunctionDef) -> bool:
    """La verificación es lo PRIMERO que hace `execute` (antes de leer o
    escribir): la primera sentencia que no es docstring llama a require."""
    body = [s for s in fn.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    return bool(body) and _calls_require(body[0])


def _use_case_classes():
    for path in sorted(USE_CASES_DIR.glob("*.py")) + EXTRA_USE_CASES:
        for node in _tree(path).body:
            if not isinstance(node, ast.ClassDef) or node.name in NOT_WRITES:
                continue
            methods = {m.name: m for m in node.body if isinstance(m, ast.FunctionDef)}
            if "execute" in methods:
                yield path, node, methods


def _violations_for(path, node, methods) -> list[str]:
    problems = []
    init = methods.get("__init__")
    params = [] if init is None else [a.arg for a in init.args.args + init.args.kwonlyargs]
    if "authorization" not in params:
        problems.append(f"{path.name}:{node.name}.__init__ no recibe `authorization`")
    elif "unwired(" not in ast.unparse(init):
        problems.append(f"{path.name}:{node.name}.__init__ no usa `unwired(...)` como default")
    if not _first_statement_requires(methods["execute"]):
        problems.append(f"{path.name}:{node.name}.execute no empieza con require()")
    return problems


def test_every_configuracion_write_use_case_authorizes_in_backend():
    found = list(_use_case_classes())
    assert len(found) >= 81, f"se esperaban ≥81 casos de uso, hay {len(found)}"
    problems = [p for item in found for p in _violations_for(*item)]
    assert not problems, "\n".join(problems)


def test_ticket_designer_takes_an_authorizer_and_print_test_requires():
    cls = next(n for n in _tree(TICKET_DESIGNER).body
               if isinstance(n, ast.ClassDef) and n.name == "TicketDesignerService")
    methods = {m.name: m for m in cls.body if isinstance(m, ast.FunctionDef)}
    init_params = [a.arg for a in methods["__init__"].args.args + methods["__init__"].args.kwonlyargs]
    assert "authorization" in init_params
    assert TICKET_DESIGNER_WRITES <= set(methods)
    assert _first_statement_requires(methods["print_test"])
    # Los de logos delegan en casos de uso que ya verifican: deben pasarles el autorizador.
    for name in TICKET_DESIGNER_WRITES - {"print_test"}:
        source = ast.unparse(methods[name])
        assert "authorization=self._authz" in source, name


def _route_constructions_without_authorizer(source: str) -> list[str]:
    missing = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        name = node.func.id
        if not (name.endswith("UseCase") or name == "TicketDesignerService"):
            continue
        if not any(k.arg == "authorization" for k in node.keywords):
            missing.append(f"{name} (línea {node.lineno})")
    return missing


def test_composition_passes_an_authorizer_to_every_use_case():
    missing = _route_constructions_without_authorizer(ROUTES.read_text(encoding="utf-8"))
    assert not missing, "Construidos sin authorization=: " + ", ".join(missing)


def test_the_guard_detects_a_missing_authorizer():
    """La guardia se pone roja si se quita `authorization=` de una construcción."""
    assert _route_constructions_without_authorizer(
        "def f(c, a):\n    X = CreateThemeUseCase(c)\n    Y = CreateThemeUseCase(c, authorization=a)\n"
    ) == ["CreateThemeUseCase (línea 2)"]
