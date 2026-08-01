"""Produce a machine-readable inventory of the current Procurement desktop route.

This is a Phase 0 observation tool, not an acceptance test.  It deliberately
records current defects without making the suite depend on those defects.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PURCHASING = REPO / "frontend/desktop/modules/purchasing"


def _source(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def _literal_calls(source: str, method: str) -> list[str]:
    values: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != method or not node.args:
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
    return values


def collect_baseline() -> dict:
    loader = _source("core/ui/module_loader.py")
    wrapper = _source("modulos/compras_enterprise.py")
    shell = _source("frontend/desktop/modules/purchasing/purchasing_module_shell.py")
    pages = _source("frontend/desktop/modules/purchasing/pages/enterprise_pages.py")
    direct = _source("frontend/desktop/modules/purchasing/pages/direct_purchase_create_page.py")
    permission_literals = _literal_calls(shell, "can") + _literal_calls(pages, "can")
    placeholder_routes = []
    tree = ast.parse(shell)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "_route" or len(node.args) < 2:
            continue
        label, page = node.args[:2]
        if (isinstance(label, ast.Constant) and isinstance(label.value, str)
                and isinstance(page, ast.Call) and isinstance(page.func, ast.Attribute)
                and page.func.attr == "_placeholder"):
            placeholder_routes.append(label.value)
    return {
        "runtime_route": {
            "registry_key": "compras",
            "registry_target_present": '"modulos.compras_enterprise"' in loader,
            "wrapper_calls_enterprise_route": "create_enterprise_purchasing_view" in wrapper,
        },
        "permission_literals": sorted(set(permission_literals)),
        "placeholder_routes": placeholder_routes,
        "direct_purchase": {
            "capture_and_history_share_page": (
                "_build_capture_card()" in direct and "_build_recent_card()" in direct),
            "simultaneous_document_actions": [
                label for label in (
                    "Guardar compra", "Autorizar en caliente", "Confirmar y recibir", "Reversar")
                if label in direct
            ],
            "page_header_inside_shell_route": "PageHeader(" in direct,
        },
    }


if __name__ == "__main__":
    print(json.dumps(collect_baseline(), indent=2, ensure_ascii=False, sort_keys=True))
