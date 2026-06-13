import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCHED = [
    ROOT / "modulos/inventario_local.py",
    ROOT / "backend/application/queries/inventory_query_service.py",
]


def test_inventory_has_no_silent_exception_pass() -> None:
    violations: list[str] = []
    for path in WATCHED:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.body:
                non_doc_nodes = [stmt for stmt in node.body if not (isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant))]
                if len(non_doc_nodes) == 1 and isinstance(non_doc_nodes[0], ast.Pass):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == []
