"""§15 — cero imports hacia namespaces fuera de `frontend/` y `backend/`.

Este test NACE EN ROJO a propósito. Mide la deuda real de la reconstrucción
(80 imports en 62 archivos al escribirlo, HEAD `a35b8bab`) y sólo pasa a verde
cuando esa deuda llega a cero.

§16 prohíbe explícitamente resolverlo con una allowlist: no existe
`LEGACY_IMPORT_ALLOWLIST` ni equivalente, y añadir una sería falsear el gate.
La única forma de ponerlo en verde es recrear cada responsabilidad en su capa
correcta dentro de `backend/` o `frontend/`.

El inventario y la matriz responsabilidad→destino están en
`backend/docs/NEW_ARCHITECTURE_RECOVERY_AUDIT.md`.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("frontend", "backend")

#: Namespaces raíz que dejaron de ser código de aplicación válido (§1).
#: `tests` no está aquí: las pruebas viven fuera de las dos raíces por diseño.
FORBIDDEN_ROOTS = frozenset({
    "core", "modulos", "interfaz", "ui", "services", "repositories",
    "database", "application", "infrastructure", "integrations",
    "security", "sync", "hardware", "delivery", "api", "domain",
    "notifications", "utils", "tools", "migrations", "scripts", "webapp",
})


def _python_files():
    for root in SCAN_ROOTS:
        base = APP_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def _forbidden_imports(path: Path):
    """(línea, módulo) de cada import a un namespace raíz prohibido.

    Los imports relativos se ignoran: siempre resuelven dentro del propio
    paquete, así que nunca pueden apuntar fuera de `frontend`/`backend`.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_ROOTS:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module.split(".")[0] in FORBIDDEN_ROOTS:
                hits.append((node.lineno, node.module))
    return hits


def _collect():
    offenders = []
    for path in _python_files():
        relative = path.relative_to(APP_ROOT).as_posix()
        for lineno, module in _forbidden_imports(path):
            offenders.append((relative, lineno, module))
    return offenders


def test_no_forbidden_root_namespace_imports():
    offenders = _collect()
    if not offenders:
        return

    from collections import Counter

    por_modulo = Counter(module for _, _, module in offenders)
    archivos = len({relative for relative, _, _ in offenders})
    detalle = "\n  ".join(
        f"{count:3}  {module}" for module, count in por_modulo.most_common())
    raise AssertionError(
        f"{len(offenders)} imports prohibidos en {archivos} archivos "
        f"({len(por_modulo)} módulos distintos).\n"
        f"Recrea la responsabilidad en backend/ o frontend/ — no el namespace, "
        f"y sin allowlist (§16).\n  {detalle}"
    )


def test_main_is_only_a_launcher():
    """§0/§2: `main.py` no puede importar nada fuera de `frontend.desktop`."""
    main_py = APP_ROOT / "main.py"
    if not main_py.exists():
        return

    tree = ast.parse(main_py.read_text(encoding="utf-8", errors="ignore"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.append(node.module)

    ajenos = sorted({
        m for m in modules
        if m.split(".")[0] in FORBIDDEN_ROOTS
        or (m.split(".")[0] not in ("frontend", "sys", "os") and "." not in m
            and m not in ("logging", "traceback"))
    })
    assert not ajenos, (
        "`main.py` debe ser sólo el launcher de `frontend.desktop.app`; "
        f"importa además: {ajenos}")
