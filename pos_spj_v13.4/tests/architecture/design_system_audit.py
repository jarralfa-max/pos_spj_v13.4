"""Reproducible AST audit of desktop visual debt; no runtime Qt dependency.

The baseline records exact offending expressions with multiplicity. It is never
an exemption for a whole file, module, or rule. Geometry checks here only detect
provable literal constraints; runtime viewport and touch checks remain necessary.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("design_system_debt_baseline.json")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
EMOJI = re.compile(r"[\U0001f300-\U0001faff\u2600-\u27bf]")
CANONICAL_PAGES = {
    "StandardPage", "ScrollablePage", "DashboardPage", "WorklistPage", "FormPage",
    "MasterDetailPage", "SplitPage", "TabbedPage", "WizardPage", "POSPage",
    "StandardWindow", "ApplicationWindow", "StandardDialog",
}
OVERFLOW_HOSTS = CANONICAL_PAGES | {"PageViewport", "ContentHost", "QScrollArea"}
CONTROLS = {
    "QPushButton", "QToolButton", "QLineEdit", "QComboBox", "QSpinBox",
    "QDoubleSpinBox", "PrimaryButton", "SecondaryButton", "GhostButton",
    "DangerButton", "IconButton", "StandardLineEdit", "SearchInput",
    "MoneyInput", "DecimalInput", "IntegerInput", "WeightInput", "PhoneInput",
    "EmailInput", "PasswordInput", "StandardComboBox",
}


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int
    expression: str
    fingerprint: str

    @property
    def key(self):
        return self.path, self.rule, self.fingerprint


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + "." + node.attr
    return ""


def scan_source(source: str, path: str) -> list[Finding]:
    tree = ast.parse(source, filename=path)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases.update({item.asname or item.name: item.name for item in node.names})
    def symbol(node):
        name = _name(node).rsplit(".", 1)[-1]
        return aliases.get(name, name)

    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    controls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if symbol(node.value.func) in CONTROLS:
                for target in node.targets:
                    controls[_name(target)] = symbol(node.value.func)

    findings = []
    canonical_component = path.startswith("frontend/desktop/components/")
    theme_infrastructure = path.startswith("frontend/desktop/themes/")
    web_infrastructure = path.startswith("frontend/desktop/charts/")

    def add(rule, node, identity=None):
        expression = ast.unparse(node) if identity is None else identity
        normalized = ast.dump(node, include_attributes=False) if identity is None else identity
        findings.append(Finding(path, rule, node.lineno, expression,
                                hashlib.sha256(normalized.encode()).hexdigest()[:20]))

    def owning_class(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, ast.ClassDef):
                return node
        return None

    def is_print_canvas_data(node):
        # This is the white physical card stock in the existing declarative
        # print example, not a native-widget color. Keep the exception tied to
        # its path, JSON schema assignment, exact value, and canvas structure.
        if path != "frontend/desktop/modules/tarjetas_fidelidad/pages/templates_page.py" or node.value != "#FFFFFF":
            return False
        container = parents.get(node)
        if not isinstance(container, ast.Dict):
            return False
        entries = {key.value: value for key, value in zip(container.keys, container.values)
                   if isinstance(key, ast.Constant)}
        if entries.get("background_color") is not node or not {"width_mm", "height_mm"} <= entries.keys():
            return False
        current = container
        while current in parents:
            current = parents[current]
            if isinstance(current, ast.Assign):
                return (any(isinstance(target, ast.Name) and target.id == "_EXAMPLE_SCHEMA" for target in current.targets)
                        and isinstance(current.value, ast.Call) and _name(current.value.func) == "json.dumps")
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = symbol(node.func)
            if isinstance(node.func, ast.Attribute):
                method = node.func.attr
                if method == "setStyleSheet" and not theme_infrastructure:
                    add("inline_qss", node)
                if method in {"setFixedHeight", "setFixedWidth", "setFixedSize"}:
                    receiver = _name(node.func.value)
                    owner = owning_class(node)
                    is_control = receiver in controls or (
                        receiver == "self" and owner is not None
                        and any(symbol(base) in CONTROLS for base in owner.bases)
                    )
                    if is_control and any(isinstance(arg, ast.Constant)
                                          and type(arg.value) in {int, float}
                                          and 0 < arg.value < 48 for arg in node.args):
                        add("fixed_control_below_touch_target", node)
                if method in {"setFixedSize", "setMinimumSize", "resize"}:
                    owner = owning_class(node)
                    if owner and any(symbol(base) in {"QDialog", "StandardDialog"} for base in owner.bases):
                        values = [arg.value if isinstance(arg, ast.Constant) else None for arg in node.args]
                        if len(values) >= 2 and any(type(value) in {int, float} and value > limit
                                                   for value, limit in zip(values[:2], (1280, 720))):
                            add("dialog_geometry_exceeds_smallest_viewport", node)
            if call == "QTableWidget" and not canonical_component:
                add("native_operational_table", node)
            if call == "QDialog" and not canonical_component:
                add("noncanonical_dialog", node)
        elif isinstance(node, ast.ClassDef) and not canonical_component:
            bases = {symbol(base) for base in node.bases}
            identity = f"class {node.name}({', '.join(sorted(bases))})"
            if node.name.endswith(("KPICard", "PageHeader")) or node.name in {"KPICard", "PageHeader"}:
                add("local_standard_component", node, identity)
            if "QTableWidget" in bases:
                add("native_operational_table", node, identity)
            if "QDialog" in bases:
                add("noncanonical_dialog", node, identity)
            if bases & {"QPushButton", "QLineEdit"}:
                customized = any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                                 and child.func.attr in {"setStyleSheet", "setPalette", "setFont", "paintEvent"}
                                 for child in ast.walk(node))
                customized |= any(isinstance(child, ast.FunctionDef) and child.name == "paintEvent"
                                  for child in node.body)
                if customized:
                    add("local_visual_control", node, identity)
            screen_location = "/pages/" in path or Path(path).stem.endswith(("_page", "_view", "_window", "_workspace"))
            screen_name = node.name.endswith(("Page", "Window", "Workspace", "View", "Screen"))
            if bases & {"QWidget", "QMainWindow"} and (screen_name or screen_location):
                uses_overflow = any(isinstance(child, ast.Call) and symbol(child.func) in OVERFLOW_HOSTS
                                    for child in ast.walk(node))
                if not uses_overflow:
                    add("screen_without_explicit_overflow", node, identity)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if not theme_infrastructure and not web_infrastructure and HEX.search(node.value) and not is_print_canvas_data(node):
                add("hardcoded_visual_hex", node)
            if not theme_infrastructure and EMOJI.search(node.value):
                add("unicode_icon_literal", node)
    return findings


def sources(root: Path = REPO):
    for directory in ("frontend/desktop", "modulos", "ui"):
        for path in sorted((root / directory).rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def scan_repository(root: Path = REPO):
    return [finding for path in sources(root)
            for finding in scan_source(path.read_text(encoding="utf-8-sig"), path.relative_to(root).as_posix())]


def regressions(findings, baseline):
    """No count increase or new expression can hide behind existing file debt."""
    actual = Counter(finding.key for finding in findings)
    allowed = Counter({(entry["path"], entry["rule"], entry["fingerprint"]): entry["count"]
                       for entry in baseline["findings"]})
    return actual - allowed, allowed - actual


def summarize(findings):
    return {rule: {"occurrences": count, "files": len({item.path for item in findings if item.rule == rule})}
            for rule, count in sorted(Counter(item.rule for item in findings).items())}


def module_adoption(root: Path = REPO):
    """Source-level adoption is evidence of imports/composition, not visual approval."""
    result = {}
    for directory in sorted((root / "frontend/desktop/modules").iterdir()):
        if not directory.is_dir() or directory.name == "__pycache__":
            continue
        files = list(directory.rglob("*.py"))
        counts = Counter(files=len(files))
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            nodes = list(ast.walk(tree))
            counts["files_importing_canonical_components"] += any(
                isinstance(node, ast.ImportFrom) and (node.module or "").startswith("frontend.desktop.components")
                for node in nodes)
            counts["files_using_page_layouts"] += any(
                isinstance(node, ast.Name) and node.id in CANONICAL_PAGES | {"PageViewport"}
                for node in nodes)
            counts["files_using_standard_table"] += any(
                isinstance(node, ast.Name) and node.id == "StandardTable" for node in nodes)
        result[directory.name] = dict(counts)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print every finding and measured totals.")
    parser.add_argument("--output", type=Path, help="Write the measured report as UTF-8 JSON.")
    args = parser.parse_args()
    findings = scan_repository()
    payload = {"files_scanned": sum(1 for _ in sources()), "rules": summarize(findings),
               "module_adoption": module_adoption()}
    if args.json:
        payload["findings"] = [asdict(item) for item in findings]
    serialized = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
