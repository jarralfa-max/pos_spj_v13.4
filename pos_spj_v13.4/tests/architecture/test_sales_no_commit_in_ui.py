from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"


def test_sales_customer_creation_has_no_ui_commit() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    start = content.index("def guardar_nuevo_cliente")
    next_def = content.find("\n    def ", start + 1)
    block = content[start:] if next_def == -1 else content[start:next_def]
    assert ".commit(" not in block
    assert ".rollback(" not in block
