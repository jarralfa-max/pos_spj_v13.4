import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"


def test_sales_manual_quantity_dialogs_default_to_zero() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    assert "value=0.500" not in content
    assert "value=0.100" not in content
    assert "value=1.0" not in content
    matches = re.findall(r"QInputDialog\.getDouble\([\s\S]*?value\s*=\s*([^,\n]+)", content)
    assert "0.0" in {m.strip() for m in matches}
