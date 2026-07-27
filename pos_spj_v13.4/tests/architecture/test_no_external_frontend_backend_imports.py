import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "pos_spj_v13.4"


def test_frontend_backend_imports_resolve_inside_package() -> None:
    violations = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = node.names[0].name if node.names else ""
            root = module.split(".")[0]
            if root in {"frontend", "backend"} and not (PACKAGE_ROOT / root).exists():
                violations.append(f"{path.relative_to(REPO_ROOT)} imports {module}")
    assert not violations, "Imports point to non-package frontend/backend: " + "; ".join(violations)
