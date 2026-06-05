from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MERMA_UI = PACKAGE_ROOT / "modulos" / "merma.py"


def test_waste_ui_has_no_sql_schema_or_direct_transactions() -> None:
    source = MERMA_UI.read_text(encoding="utf-8")
    forbidden = ["SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM", "ALTER TABLE", ".commit(", ".rollback("]
    assert [token for token in forbidden if token in source.upper() or token in source] == []


def test_waste_ui_uses_canonical_services_and_search_selector() -> None:
    source = MERMA_UI.read_text(encoding="utf-8")
    assert "SearchSelector" in source
    assert "WasteApplicationService" in source
    assert "RegisterWasteUseCase" in source
    assert "WasteQueryService" in source
    assert "registrar_merma" not in source
    assert "UPDATE productos" not in source


def test_legacy_waste_application_route_was_removed() -> None:
    service_source = (PACKAGE_ROOT / "core" / "services" / "erp_application_service.py").read_text(encoding="utf-8")
    assert "def registrar_merma" not in service_source
