from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MERMA_UI = PACKAGE_ROOT / "modulos" / "merma.py"


def test_merma_uses_canonical_permissions_only() -> None:
    source = MERMA_UI.read_text(encoding="utf-8")
    assert "inventario.ajustar" not in source
    assert '"MERMA.crear"' in source
    assert '"MERMA.autorizar"' in source
