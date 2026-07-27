from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"


def test_sales_ticket_settings_use_query_service() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    assert "TicketSettingsQueryService" in content
    assert "SELECT valor FROM configuraciones" not in content
