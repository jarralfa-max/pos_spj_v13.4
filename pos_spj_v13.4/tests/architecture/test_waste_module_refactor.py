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


def test_waste_ui_stock_warning_blocks_negative_canonical_inventory() -> None:
    source = MERMA_UI.read_text(encoding="utf-8")
    assert "No se puede registrar una merma que deje inventario en negativo" in source
    assert "La existencia se ajustará a cero" not in source
    assert "la diferencia quedará documentada para auditoría" not in source


def test_waste_backend_does_not_use_legacy_inventory_sources_operationally() -> None:
    backend_files = [
        PACKAGE_ROOT / "backend" / "application" / "services" / "waste_application_service.py",
        PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "waste_repository.py",
    ]
    forbidden = [
        "decrease_inventory_for_waste",
        "inventario_actual",
        "branch_inventory",
        "movimientos_inventario",
        "UPDATE productos SET existencia",
        "p.existencia",
    ]
    violations = {
        str(path.relative_to(PACKAGE_ROOT)): [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for path in backend_files
    }
    assert {path: tokens for path, tokens in violations.items() if tokens} == {}



def test_waste_phase11_architecture_audit_documented() -> None:
    doc = PACKAGE_ROOT / "docs" / "architecture" / "WASTE_MODULE_PHASE11_AUDIT.md"
    assert doc.is_file()
    source = doc.read_text(encoding="utf-8")
    required = [
        "RegisterWasteUseCase",
        "WasteApplicationService",
        "WasteRepository",
        "WasteQueryService",
        "WasteAuthorizationService",
        "outbox",
        "auto_audit",
        "No se modifica código funcional en Fase 11",
    ]
    assert [token for token in required if token not in source] == []
