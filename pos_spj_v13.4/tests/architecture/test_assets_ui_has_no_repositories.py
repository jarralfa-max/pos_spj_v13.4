"""ASSET-1 (§6-7, §109) — the Activos UI must never import/instantiate
repositories directly; it consumes QueryServices/UseCases only.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import asset_ui_py_files, relative

_FORBIDDEN = re.compile(
    r"infrastructure\.db\.repositories"
    r"|\bRepositoryPort\b"
    r"|\bAssetRepository\b"
    r"|\bAssetCategoryRepository\b"
    r"|\bAssetLocationRepository\b"
    r"|UnitOfWork\b",
)


def test_assets_ui_has_no_repositories():
    offenders = []
    for path in asset_ui_py_files():
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "La UI de Activos referencia repositorios directamente "
        "(debe usar QueryService/UseCase):\n" + "\n".join(offenders)
    )
