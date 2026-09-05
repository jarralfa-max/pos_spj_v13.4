"""ASSET-1 (REGLA CERO, §12, §110) — no entity/dataclass field named `id` or
`*_id` may be annotated as `int` anywhere in the Assets/EAM bounded context.
AST-based so a docstring merely mentioning "int" never triggers.
"""

from __future__ import annotations

import ast

from tests.architecture.assets_guardrails import asset_backend_py_files, relative


def _annotation_is_int(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "int"


def _field_name_is_identity(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def test_assets_entities_have_no_integer_id_fields():
    offenders = []
    for path in asset_backend_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if _field_name_is_identity(node.target.id) and _annotation_is_int(node.annotation):
                    offenders.append(f"{relative(path)}:{node.lineno}: {node.target.id}: int")
            if isinstance(node, ast.arg) and node.annotation is not None:
                if _field_name_is_identity(node.arg) and _annotation_is_int(node.annotation):
                    offenders.append(f"{relative(path)}:{node.lineno}: {node.arg}: int")
    assert not offenders, (
        "campo(s) de identidad tipados como int en Activos (deben ser str/UUIDv7):\n"
        + "\n".join(offenders)
    )
