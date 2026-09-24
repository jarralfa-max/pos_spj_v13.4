"""Keep native Qt styling owned by the token builder and ThemeManager.

This audit follows executable Python calls, not CSS-looking text. HTML/JS used
by web views has a separate renderer and is not an application stylesheet.
"""

from __future__ import annotations

import ast

import pytest

from tests.architecture.design_system_audit import REPO, sources


def _style_operations(source: str):
    """Return (operation, enclosing scope, receiver) for direct Python syntax."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def scope(node):
        names = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
        return tuple(reversed(names))

    operations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"setStyleSheet", "setPalette"}:
                operations.append((node.func.attr, scope(node), ast.unparse(node.func.value)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_qss":
            operations.append(("build_qss", scope(node), ""))
    return operations


@pytest.fixture(scope="module")
def styling_inventory():
    return [
        (path.relative_to(REPO).as_posix(), operation, scope, receiver)
        for path in sources()
        for operation, scope, receiver in _style_operations(path.read_text(encoding="utf-8-sig"))
    ]


@pytest.mark.parametrize("method", ["setStyleSheet", "setPalette"])
def test_theme_manager_apply_is_the_only_native_style_writer(styling_inventory, method):
    actual = [entry for entry in styling_inventory if entry[1] == method]
    assert actual == [
        ("frontend/desktop/themes/theme_manager.py", method, ("ThemeManager", "apply"), "app")
    ], f"Native style writes must belong to ThemeManager.apply: {actual}"


def test_global_qss_has_one_builder(styling_inventory):
    actual = [entry for entry in styling_inventory if entry[1] == "build_qss"]
    assert actual == [
        ("frontend/desktop/themes/qss_builder.py", "build_qss", (), "")
    ], f"Competing QSS builders bypass global tokens: {actual}"


def test_native_qss_is_generated_instead_of_duplicated_in_files():
    stylesheets = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "frontend" / "desktop").rglob("*")
        if path.is_file() and path.suffix.lower() == ".qss"
    ]
    assert not stylesheets, f"Static QSS duplicates the token builder: {stylesheets}"


def test_style_inventory_ignores_prose_and_embedded_web_css():
    source = '''
"""Example: app.setStyleSheet(qss); widget.setPalette(palette)."""
HTML = '<style>body { color: #18372B; }</style>'
JS = 'document.body.style.background = "#FFFFFF";'
view.setHtml(HTML)
view.page().runJavaScript(JS)
'''
    assert _style_operations(source) == []


def test_style_inventory_retains_noncanonical_scopes_inside_theme_modules():
    # There is no directory-wide exemption for themes: only the exact owner
    # above can write native styling, even when another writer is a helper.
    source = '''
class AnotherTheme:
    def apply(self, app):
        app.setStyleSheet("QWidget { color: red; }")
        app.setPalette(palette)

def build_qss():
    return "QWidget { color: red; }"
'''
    operations = _style_operations(source)
    assert ("setStyleSheet", ("AnotherTheme", "apply"), "app") in operations
    assert ("setPalette", ("AnotherTheme", "apply"), "app") in operations
    assert ("build_qss", (), "") in operations


def test_style_inventory_catches_widget_overrides_in_the_canonical_method():
    operations = _style_operations('''
class ThemeManager:
    def apply(self, app):
        widget.setStyleSheet(qss)
''')
    assert operations == [("setStyleSheet", ("ThemeManager", "apply"), "widget")]
