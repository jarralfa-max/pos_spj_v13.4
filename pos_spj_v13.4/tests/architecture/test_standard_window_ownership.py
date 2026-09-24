"""Top-level Qt window policy belongs to StandardWindow, not feature modules."""
import ast
from pathlib import Path


DESKTOP = Path(__file__).resolve().parents[2] / "frontend/desktop"


def test_qmainwindow_construction_and_inheritance_have_one_owner():
    violations = []
    for path in DESKTOP.rglob("*.py"):
        if path == DESKTOP / "components/standard_window.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        aliases = {alias.asname or alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module == "PyQt5.QtWidgets"
                   for alias in node.names if alias.name == "QMainWindow"}
        for node in ast.walk(tree):
            references = node.bases if isinstance(node, ast.ClassDef) else [node.func] if isinstance(node, ast.Call) else []
            for reference in references:
                if ((isinstance(reference, ast.Name) and reference.id in aliases) or
                        (isinstance(reference, ast.Attribute) and reference.attr == "QMainWindow")):
                    violations.append(f"{path.relative_to(DESKTOP)}:{node.lineno}")
    assert not violations, "Use StandardWindow: " + ", ".join(violations)


def test_feature_modules_do_not_override_window_branding():
    violations = []
    for path in (DESKTOP / "modules").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setWindowIcon":
                violations.append(f"{path.relative_to(DESKTOP)}:{node.lineno}")
    assert not violations, "Window branding belongs to canonical windows/dialogs: " + ", ".join(violations)
