"""Desktop dialogs share the canonical window, viewport and footer owner."""

import ast
from pathlib import Path

import pytest


APP_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = APP_ROOT / "frontend" / "desktop"
CANONICAL_DIALOGS = DESKTOP / "components" / "dialogs.py"
LAYOUT_TYPES = {"QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout", "QStackedLayout"}
INPUT_METHODS = {"getText", "getItem", "getDouble", "getInt"}


def _ownership_violations(source: str) -> list[tuple[int, str]]:
    """Inspect Qt imports and aliases without importing application modules."""
    tree = ast.parse(source)
    aliases: dict[str, str] = {}

    def symbol(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{symbol(node.value)}.{node.attr}"
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
        elif isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = (
                    item.name if item.asname else item.name.split(".")[0]
                )

    # Also cover simple aliases such as NativeDialog = widgets.QDialog.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases[target.id] = symbol(node.value)

    def is_qt_type(node, names):
        name = symbol(node)
        return name in names or name in {f"PyQt5.QtWidgets.{item}" for item in names}

    def is_standard_dialog(node):
        name = symbol(node)
        return name.rsplit(".", 1)[-1] in {"StandardDialog", "FormDialog"}

    def is_self(node):
        return isinstance(node, ast.Name) and node.id == "self"

    violations = []

    class Visitor(ast.NodeVisitor):
        owns_standard_layout = False

        def visit_ClassDef(self, node):
            for native in ("QDialog", "QInputDialog"):
                if any(is_qt_type(base, {native}) for base in node.bases):
                    violations.append((node.lineno, f"native {native} base"))
            previous = self.owns_standard_layout
            self.owns_standard_layout = any(is_standard_dialog(base) for base in node.bases)
            self.generic_visit(node)
            self.owns_standard_layout = previous

        def visit_Call(self, node):
            for native in ("QDialog", "QInputDialog"):
                if is_qt_type(node.func, {native}):
                    violations.append((node.lineno, f"native {native} construction"))
            owner, _, method = symbol(node.func).rpartition(".")
            if owner in {"QInputDialog", "PyQt5.QtWidgets.QInputDialog"} and method in INPUT_METHODS:
                violations.append((node.lineno, "native QInputDialog prompt"))
            if self.owns_standard_layout:
                layout_on_self = is_qt_type(node.func, LAYOUT_TYPES) and (
                    bool(node.args and is_self(node.args[0]))
                    or any(item.arg == "parent" and is_self(item.value) for item in node.keywords)
                )
                replaces_layout = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "setLayout"
                    and is_self(node.func.value)
                )
                if layout_on_self or replaces_layout:
                    violations.append((node.lineno, "replaces StandardDialog layout"))
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


@pytest.fixture(scope="module")
def desktop_violations():
    findings = []
    for path in sorted(DESKTOP.rglob("*.py")):
        if path == CANONICAL_DIALOGS:
            continue
        for line, reason in _ownership_violations(path.read_text(encoding="utf-8-sig")):
            findings.append((reason, f"{path.relative_to(APP_ROOT).as_posix()}:{line}: {reason}"))
    return findings


def test_only_canonical_component_inherits_or_constructs_qdialog(desktop_violations):
    findings = [message for reason, message in desktop_violations if reason.startswith("native QDialog")]
    assert not findings, "Use StandardDialog or FormDialog:\n" + "\n".join(findings)


def test_standard_dialog_subclasses_preserve_the_owned_layout(desktop_violations):
    findings = [message for reason, message in desktop_violations if reason == "replaces StandardDialog layout"]
    assert not findings, "Use content_layout(), self.form or add_footer_widget():\n" + "\n".join(findings)


def test_native_input_dialogs_use_the_canonical_capture_components(desktop_violations):
    findings = [message for reason, message in desktop_violations if reason.startswith("native QInputDialog")]
    assert not findings, "Use FormDialog or the canonical numeric input dialogs:\n" + "\n".join(findings)


@pytest.mark.parametrize("source", [
    "from PyQt5.QtWidgets import QDialog\nclass Edit(QDialog): pass",
    "from PyQt5.QtWidgets import QDialog as Native\nclass Edit(Native): pass",
    "from PyQt5 import QtWidgets as W\nclass Edit(W.QDialog): pass",
    "import PyQt5.QtWidgets as W\ndialog = W.QDialog(parent)",
    "import PyQt5.QtWidgets\ndialog = PyQt5.QtWidgets.QDialog(parent)",
    "from PyQt5.QtWidgets import QDialog\nNative = QDialog\ndialog = Native()",
    "from PyQt5.QtWidgets import QInputDialog as Native\nclass Edit(Native): pass",
    "from PyQt5.QtWidgets import QInputDialog as Native\ndialog = Native()",
    "import PyQt5.QtWidgets as W\ndialog = W.QInputDialog()",
    "from PyQt5.QtWidgets import QInputDialog as Native\nvalue = Native.getText(parent, title, label)",
    "from frontend.desktop.components.dialogs import StandardDialog as Base\n"
    "from PyQt5.QtWidgets import QVBoxLayout as Layout\n"
    "class Edit(Base):\n def setup(self): Layout(self)",
    "from frontend.desktop.components import dialogs as D\n"
    "from PyQt5 import QtWidgets as W\n"
    "class Edit(D.FormDialog):\n def setup(self): W.QFormLayout(parent=self)",
    "class Edit(StandardDialog):\n def setup(self): self.setLayout(layout)",
])
def test_guard_detects_aliases_and_layout_replacement(source):
    assert len(_ownership_violations(source)) == 1


@pytest.mark.parametrize("method", sorted(INPUT_METHODS))
def test_guard_detects_aliased_native_prompt_methods(method):
    source = (
        "from PyQt5 import QtWidgets as W\n"
        "Native = W.QInputDialog\n"
        f"prompt = Native.{method}\n"
        "value = prompt(parent, title, label)"
    )
    assert _ownership_violations(source) == [(4, "native QInputDialog prompt")]


@pytest.mark.parametrize("source", [
    "from PyQt5.QtWidgets import QDialog\naccepted = dialog.exec_() == QDialog.Accepted",
    "from PyQt5 import QtWidgets as W\nrejected = W.QDialog.Rejected",
    "from PyQt5.QtWidgets import QFileDialog, QMessageBox\n"
    "picker = QFileDialog()\nmessage = QMessageBox()",
    "class Edit(StandardDialog):\n def setup(self):\n"
    "  root = self.content_layout()\n  footer = QWidget(self)\n"
    "  buttons = QHBoxLayout(footer)\n  self.add_footer_widget(footer)",
    "class Edit(FormDialog):\n def setup(self): self.form.addRow(label, field)",
    "from frontend.desktop.components.dialogs import FormDialog as Capture\n"
    "value = Capture.get_text(parent, title, label)\n"
    "item = Capture.get_item(parent, title, label, items)",
    "class Page(QWidget):\n def setup(self): QVBoxLayout(self)",
    "class Edit(StandardDialog):\n class Body(QWidget):\n"
    "  def setup(self): QVBoxLayout(self)",
])
def test_guard_allows_result_constants_native_selectors_and_content_layouts(source):
    assert _ownership_violations(source) == []
