import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_logistics_ddl_exists_only_in_migration():
    offenders = []
    for base in (ROOT / "backend", ROOT / "frontend"):
        for path in base.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "CREATE TABLE" in source or "ALTER TABLE" in source:
                if "logistics" in str(path).lower():
                    offenders.append(str(path.relative_to(ROOT)))
    assert not offenders
    migration = ROOT / "migrations/standalone/171_logistics_bounded_context_schema.py"
    assert migration.exists() and "logistics_physical_containers" in migration.read_text()
    engine = (ROOT / "migrations/engine.py").read_text(encoding="utf-8")
    assert '"171",  "migrations.standalone.171_logistics_bounded_context_schema"' in engine


def test_logistics_domain_has_no_sql_or_float_conversion():
    for path in (ROOT / "backend/domain/logistics").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "SELECT " not in source and "INSERT " not in source
        assert "float(" not in source
        ast.parse(source)


def test_procurement_does_not_own_new_logistics_tables():
    procurement_schema = (
        ROOT / "backend/infrastructure/db/schema/procurement_schema.py"
    ).read_text(encoding="utf-8")
    for table in ("logistics_shipments", "logistics_physical_containers",
                  "logistics_shipment_nodes", "logistics_container_seals"):
        assert table not in procurement_schema


def test_logistics_runtime_wiring_is_called_from_composition_root():
    wiring = (ROOT / "core/events/wiring.py").read_text(encoding="utf-8")
    assert "_wire_logistics_pipeline(bus, container)" in wiring
    assert "wire_logistics(bus, service)" in wiring
    engine = (ROOT / "migrations/engine.py").read_text()
    assert '"172",  "migrations.standalone.172_logistics_loading_authorizations"' in engine


def test_origin_purchase_workspace_is_operational_not_placeholder():
    page = (ROOT / "frontend/desktop/modules/purchasing/pages/logistics_related_page.py").read_text()
    coordinator = (ROOT / "backend/application/logistics/origin_purchase_workspace.py").read_text()
    assert "originPurchaseWorkspacePage" in page
    assert all(value in page for value in (
        "Crear o abrir embarque", "Abrir sesión móvil", "Asignación de líneas",
        "Diferencias y autorizaciones", "Autorizar diferencia seleccionada",
        "Sellar raíz", "Confirmar despacho"))
    assert all(value in coordinator for value in (
        "create_shipment", "mobile_handoff", "seal_root", "dispatch"))
    assert "LogisticsApplicationService" not in page
