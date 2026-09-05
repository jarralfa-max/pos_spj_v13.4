"""ASSET-1 (§109-110) — the new Assets/EAM bounded context never imports the
legacy `modulos.activos` / `core.services.asset_service` god-module, nor the
orphaned/abandoned scaffolding flagged in the ASSET-0 audit as probable
DELETE_DUPLICATE. New code must not build on top of what it's meant to
replace.
"""

from __future__ import annotations

from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, asset_py_files, relative

_FORBIDDEN_IMPORTS = (
    "modulos.activos",
    "core.services.asset_service",
    "backend.application.commands.asset_commands",
    "backend.application.queries.asset_query_service",
    "backend.application.use_cases.create_asset_use_case",
)


def test_assets_module_does_not_import_legacy_or_orphaned_code():
    offenders = []
    for path in asset_py_files(ALL_ASSET_CODE_ROOTS):
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_IMPORTS:
            if token in text:
                offenders.append(f"{relative(path)}: imports/references {token!r}")
    assert not offenders, (
        "El bounded context nuevo de Activos referencia código legacy/huérfano "
        "que debe reemplazar, no envolver:\n" + "\n".join(offenders)
    )
