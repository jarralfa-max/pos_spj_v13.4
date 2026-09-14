"""Actual navigation/header icon contracts must have named vector artwork."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from frontend.desktop.components.icons import Icons, _ACCESSIBLE_NAMES, _PATHS, all_icons


DESKTOP = Path(__file__).resolve().parents[2] / "frontend" / "desktop"


def _sidebar_icon_omissions(source: str):
    """Find default icons on known sidebar instances, without importing modules.

    Constructor imports and simple instance aliases identify receivers. Local
    variables belong to their function; ``self`` attributes belong to their
    class so navigation built in a separate method is checked too.
    """
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
    constructors = {
        f"{module}.{name}"
        for module in (
            "frontend.desktop.components", "frontend.desktop.components.side_nav",
        )
        for name in ("SideNav", "ModuleSidebar")
    }

    def qualified_name(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{qualified_name(node.value)}.{node.attr}"
        return ""

    def receiver_key(node):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            return None
        scope = node
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        instance_attribute = isinstance(node, ast.Attribute) and isinstance(root, ast.Name) and root.id == "self"
        scope_types = (ast.ClassDef,) if instance_attribute else (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        while scope in parents:
            scope = parents[scope]
            if isinstance(scope, scope_types):
                break
        return scope, ast.unparse(node)

    receivers = set()

    def is_sidebar(node):
        if isinstance(node, ast.Call):
            return qualified_name(node.func) in constructors
        if isinstance(node, ast.Name) and node.id == "self":
            scope = node
            while scope in parents:
                scope = parents[scope]
                if isinstance(scope, ast.ClassDef):
                    return any(qualified_name(base) in constructors for base in scope.bases)
        return receiver_key(node) in receivers

    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assignments.extend((target, node.value) for target in node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assignments.append((node.target, node.value))
    # Resolve aliases even when a class's methods appear before __init__.
    while True:
        found = {
            receiver_key(target) for target, value in assignments
            if receiver_key(target) is not None and is_sidebar(value)
        }
        if found <= receivers:
            break
        receivers.update(found)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"add_section", "add_group"}
                and is_sidebar(node.func.value)):
            continue
        icon = next((kw.value for kw in node.keywords if kw.arg == "icon"), None)
        if icon is None and len(node.args) > 1 and not isinstance(node.args[1], ast.Starred):
            icon = node.args[1]
        if icon is None or (isinstance(icon, ast.Constant) and (
                icon.value is None or isinstance(icon.value, str) and not icon.value.strip())):
            yield node.lineno, node.func.attr


def _references(source: str):
    """Read icon arguments, not arbitrary Spanish labels, DTO data or prose."""
    tree = ast.parse(source)
    catalogs, providers = {"Icons"}, {"IconProvider"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
                "frontend.desktop.components.icons", "frontend.desktop.components"}:
            for alias in node.names:
                if alias.name == "Icons":
                    catalogs.add(alias.asname or alias.name)
                elif alias.name == "IconProvider":
                    providers.add(alias.asname or alias.name)
    nav_positions = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("NavEntry"):
            fields = [field.target.id for field in node.body
                      if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name)]
            if "icon" in fields:
                nav_positions[node.name] = fields.index("icon")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in catalogs:
            yield node.lineno, "constant", node.attr
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        if (name == "getattr" and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name) and node.args[0].id in catalogs
                and isinstance(node.args[1], ast.Constant)):
            yield node.lineno, "constant", node.args[1].value
        candidates = []
        if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id in providers and node.func.attr in {"icon", "pixmap", "bind"}):
            index = 1 if node.func.attr == "bind" else 0
            if len(node.args) > index:
                candidates.append(node.args[index])
            candidates.extend(kw.value for kw in node.keywords if kw.arg == "name")
        if name in {"IconButton", "create_icon_button"}:
            index = 1 if name == "create_icon_button" else 0
            if len(node.args) > index:
                candidates.append(node.args[index])
            candidates.extend(kw.value for kw in node.keywords if kw.arg == "icon")
        if name in nav_positions and len(node.args) > nav_positions[name]:
            candidates.append(node.args[nav_positions[name]])
        if name in nav_positions or name in {"PageHeader", "KPIDTO", "NavigationItemDefinition"}:
            candidates.extend(kw.value for kw in node.keywords if kw.arg == "icon")
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"add_section", "add_group"}:
            if len(node.args) > 1:
                candidates.append(node.args[1])
            candidates.extend(kw.value for kw in node.keywords if kw.arg == "icon")
        for candidate in candidates:
            if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                yield node.lineno, "identifier", candidate.value


def test_navigation_and_headers_only_request_registered_icons():
    missing = []
    for path in DESKTOP.rglob("*.py"):
        for line, kind, name in _references(path.read_text(encoding="utf-8-sig")):
            if (kind == "constant" and not hasattr(Icons, name)) or (kind == "identifier" and name not in _PATHS):
                missing.append(f"{path.relative_to(DESKTOP)}:{line}: {kind} {name}")
    assert not missing, "Missing icon contracts:\n" + "\n".join(missing)


def test_module_sidebars_supply_explicit_icons_for_sections_and_groups():
    missing = []
    for path in (DESKTOP / "modules").rglob("*.py"):
        for line, method in _sidebar_icon_omissions(path.read_text(encoding="utf-8-sig")):
            missing.append(f"{path.relative_to(DESKTOP)}:{line}: {method} requires an explicit icon")
    assert not missing, "Module sidebar entries must not inherit the default icon:\n" + "\n".join(missing)


@pytest.mark.parametrize("base, expected", [("SideNav", [(4, "add_section")]), ("QWidget", [])])
def test_sidebar_guardrail_checks_inherited_sidebar_methods(base, expected):
    source = ("from frontend.desktop.components import SideNav\n"
              f"class Navigation({base}):\n"
              " def populate(self):\n"
              "  self.add_section('Inventario')\n")
    assert list(_sidebar_icon_omissions(source)) == expected


def test_catalog_has_vector_and_spanish_accessibility_name_for_every_constant():
    values = {value for key, value in vars(Icons).items() if key.isupper()}
    assert values == set(all_icons()) == set(_PATHS) == set(_ACCESSIBLE_NAMES)
    for name in values:
        assert _ACCESSIBLE_NAMES[name].strip() and _ACCESSIBLE_NAMES[name] != name
        assert "<path " in _PATHS[name] or "<rect " in _PATHS[name] or "<circle " in _PATHS[name]


@pytest.mark.parametrize("source, expected", [
    ('class SectionNavEntry:\n page_id: str\n title: str\n icon: str\nSectionNavEntry("page", "Etiqueta", "missing")', [(5, "identifier", "missing")]),
    ('PageHeader(title="missing", icon="search")', [(1, "identifier", "search")]),
    ('PageHeader(icon=getattr(Icons, "MISSING", None))', [(1, "constant", "MISSING")]),
    ('nav.add_section("Etiqueta", "search")', [(1, "identifier", "search")]),
    ('IconProvider.icon("missing")', [(1, "identifier", "missing")]),
    ('from frontend.desktop.components.icons import IconProvider as IP\nIP.bind(button, "missing")', [(2, "identifier", "missing")]),
    ('from frontend.desktop.components.icons import Icons as I\nPageHeader(icon=I.MISSING)', [(2, "constant", "MISSING")]),
    ('IconButton("missing", "Descripción")', [(1, "identifier", "missing")]),
    ('text = "Icons.MISSING"\nvalue = {"icon": "external data"}', []),
])
def test_icon_reference_detection_is_scoped_to_icon_contracts(source, expected):
    assert list(_references(source)) == expected


@pytest.mark.parametrize("statement, expected", [
    ('nav.add_section("Productos")', [(3, "add_section")]),
    ('nav.add_group("Catálogo")', [(3, "add_group")]),
    ('nav.add_section("Productos", None)', [(3, "add_section")]),
    ('nav.add_group("Catálogo", icon=None)', [(3, "add_group")]),
    ('nav.add_section("Productos", "")', [(3, "add_section")]),
    ('nav.add_section("Productos", icon="  ")', [(3, "add_section")]),
    ('nav.add_section("Productos", Icons.PACKAGE)', []),
    ('nav.add_group("Catálogo", icon=group.icon)', []),
    ('nav.add_section(label="Productos", icon="search", badge=0)', []),
    ('nav.add_section("Productos", icon=SECTION_ICONS[route.key])', []),
    ('registry.add_group("Grupo de permisos")', []),
])
def test_sidebar_guardrail_checks_positional_and_keyword_icons(statement, expected):
    source = "from frontend.desktop.components.side_nav import SideNav\nnav = SideNav()\n" + statement
    assert list(_sidebar_icon_omissions(source)) == expected


@pytest.mark.parametrize("source, expected", [
    ('from frontend.desktop.components import SideNav as Navigation\nnav = Navigation()\nnav.add_section("Productos")', [(3, "add_section")]),
    ('from frontend.desktop.components.side_nav import ModuleSidebar\nnav = ModuleSidebar()\nnav.add_group("Catálogo")', [(3, "add_group")]),
    ('import frontend.desktop.components.side_nav as widgets\nnav = widgets.SideNav()\nnav.add_section("Productos")', [(3, "add_section")]),
    ('from frontend.desktop.components.side_nav import SideNav\nnav = SideNav()\nother = nav\nother.add_section("Productos")', [(4, "add_section")]),
    ('from frontend.desktop.components.side_nav import SideNav\nSideNav().add_section("Productos")', [(2, "add_section")]),
    ('from external_package import SideNav\nnav = SideNav()\nnav.add_group("Grupo externo")', []),
    ('from frontend.desktop.components import SideNav\ndef build():\n nav = SideNav()\ndef unrelated():\n nav = Registry()\n nav.add_group("Grupo de permisos")', []),
    ('from frontend.desktop.components import SideNav\nclass Workspace:\n def populate(self):\n  self.nav.add_section("Productos")\n def __init__(self):\n  self.nav = SideNav()\nclass Other:\n def __init__(self):\n  self.nav = Registry()\n  self.nav.add_group("Permisos")', [(4, "add_section")]),
])
def test_sidebar_guardrail_tracks_navigation_receivers_and_aliases(source, expected):
    assert list(_sidebar_icon_omissions(source)) == expected
