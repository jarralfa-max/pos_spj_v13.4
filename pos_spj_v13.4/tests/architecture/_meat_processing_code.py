"""Lectura de CÓDIGO de Procesamiento para los guardarraíles §26: nombres,
importaciones y cadenas del programa, sin comentarios ni docstrings (lo que
explica el código no es el código)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Lo que corre al EJECUTAR una orden (después de congelar su definición).
EXECUTION_MODULES = (
    "backend/application/meat_processing/use_cases/order_execution_use_cases.py",
    "backend/application/meat_processing/use_cases/consumption_weighing_use_cases.py",
    "backend/application/meat_processing/use_cases/output_use_cases.py",
    "backend/application/meat_processing/use_cases/execution_use_cases.py",
    "backend/application/meat_processing/use_cases/yield_use_cases.py",
    "backend/application/meat_processing/use_cases/quality_use_cases.py",
    "backend/application/meat_processing/use_cases/processing_order_use_cases.py",
    "backend/application/meat_processing/queries/processing_order_execution_query_service.py",
    "backend/infrastructure/integrations/meat_processing_ports.py",
    "backend/infrastructure/integrations/meat_processing_execution_ports.py",
    "backend/domain/meat_processing/services/processing_execution_strategy.py",
)

#: Todo el código productivo de Procesamiento (dominio, aplicación, sus
#: integraciones y su composición).
def production_files() -> list[Path]:
    archivos: list[Path] = []
    for raiz in ("backend/domain/meat_processing", "backend/application/meat_processing",
                 "backend/infrastructure/db/repositories/meat_processing",
                 "backend/application/event_handlers/meat_processing"):
        archivos += sorted((ROOT / raiz).rglob("*.py"))
    archivos += sorted((ROOT / "backend/infrastructure/integrations").glob("meat_processing*.py"))
    archivos.append(ROOT / "backend/infrastructure/desktop/meat_processing_factory.py")
    return [a for a in archivos if "__pycache__" not in a.parts]


def tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _docstrings(modulo: ast.Module) -> set[int]:
    ids = set()
    for nodo in ast.walk(modulo):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            cuerpo = nodo.body
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(
                    getattr(cuerpo[0], "value", None), ast.Constant):
                ids.add(id(cuerpo[0].value))
    return ids


def imported_modules(path: Path) -> set[str]:
    modulos = set()
    for nodo in ast.walk(tree(path)):
        if isinstance(nodo, ast.Import):
            modulos |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.add(nodo.module)
            modulos |= {f"{nodo.module}.{a.name}" for a in nodo.names}
    return modulos


def code_strings(path: Path) -> list[tuple[int, str]]:
    """Cadenas del programa (no docstrings)."""
    modulo = tree(path)
    docs = _docstrings(modulo)
    return [(n.lineno, n.value) for n in ast.walk(modulo)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def identifiers(path: Path) -> list[tuple[int, str]]:
    salida = []
    for n in ast.walk(tree(path)):
        if isinstance(n, ast.Name):
            salida.append((n.lineno, n.id))
        elif isinstance(n, ast.Attribute):
            salida.append((n.lineno, n.attr))
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            salida.append((n.lineno, n.name))
        elif isinstance(n, ast.keyword) and n.arg:
            salida.append((getattr(n.value, "lineno", 0), n.arg))
    return salida


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
