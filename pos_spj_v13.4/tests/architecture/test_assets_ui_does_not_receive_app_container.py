"""ASSET-1 (§15, §109) — the Activos UI must never receive AppContainer whole.

No `container.db`, no `self.container = container`, no legacy `conexion.db`
reach-through — every dependency is injected explicitly.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import asset_ui_py_files, relative

_APPCONTAINER_RE = re.compile(
    r"\bAppContainer\b"
    r"|\bself\.container\s*=\s*container\b"
    r"|\bcontainer\s*=\s*container\b"
    r"|\bcontainer\.db\b"
    r"|\bcontainer\.asset_service\b"
    r"|\bconexion\.db\b"
    r"|\bconexion\.container\b",
)


def test_assets_ui_does_not_receive_app_container():
    offenders = []
    for path in asset_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _APPCONTAINER_RE.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "La UI de Activos recibe AppContainer completo o accede a container.db:\n"
        + "\n".join(offenders)
    )
