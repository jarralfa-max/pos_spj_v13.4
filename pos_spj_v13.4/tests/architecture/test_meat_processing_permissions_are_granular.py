from pathlib import Path

from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


ROOT = Path(__file__).resolve().parents[2]


def test_meat_processing_reuses_the_canonical_produccion_module_key():
    """§3/§64: one canonical route per functional area — no parallel module key
    for the same sidebar entry (interfaz/menu_lateral.py: "Procesamiento Cárnico"
    → "PRODUCCION")."""
    assert "PRODUCCION" in CANONICAL_MODULE_PERMISSIONS
    assert "PROCESAMIENTO_CARNICO" not in CANONICAL_MODULE_PERMISSIONS


def test_produccion_catalog_entry_is_granular_not_the_old_two_action_stub():
    actions = CANONICAL_MODULE_PERMISSIONS["PRODUCCION"]
    assert len(actions) > 40
    assert "orden.crear" in actions
    assert "orden.cerrar" in actions
    assert "peso.capturar_manual" in actions
    assert "sacrificio.acceso" in actions
    # the pre-relocation stub only had these two, coarse and ungranular
    assert actions != ["ver", "ejecutar"]


def test_meat_processing_domain_never_imports_from_legacy_production_modules():
    domain_dir = ROOT / "backend/domain/meat_processing"
    application_dir = ROOT / "backend/application/meat_processing"
    forbidden = ("core.production", "core.use_cases.produccion",
                 "core.services.production_application_service", "modulos.produccion")
    for path in list(domain_dir.rglob("*.py")) + list(application_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"{path} references legacy module {needle}"
