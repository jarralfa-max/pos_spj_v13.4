from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_procurement_and_qr_legacy_runtime_is_absent():
    forbidden = (
        "modulos/recepcion_qr_widget.py", "modulos/compra_directa.py",
        "core/services/recepcion_qr_service.py", "core/services/purchase_service.py",
        "application/purchases", "repositories/purchase_repository.py",
        "repositories/purchase_order_repository.py", "repositories/purchase_request_repository.py",
        "backend/infrastructure/db/repositories/compras_read_repository.py",
        "backend/infrastructure/db/repositories/compras_write_repository.py",
    )
    assert not [path for path in forbidden if (ROOT / path).exists()]


def test_navigation_has_one_canonical_purchasing_route():
    """El cargador legacy (core/ui/module_loader.py) ya no existe: la navegación
    viva es la del menú de la shell. Compras tiene UNA entrada y ninguna ruta
    paralela (auditoría Compras d9f2bca: prueba heredada actualizada)."""
    assert not (ROOT / "core/ui/module_loader.py").exists()
    navigation = (ROOT / "frontend/desktop/shell/sidebar/migrated_modules_navigation.py"
                  ).read_text(encoding="utf-8")
    assert navigation.count("module_id=PURCHASING_MODULE_ID") == 1
    for duplicate in ("compras_pro", "compra_directa", "compras_enterprise"):
        assert duplicate not in navigation


def test_procurement_desktop_reads_logistics_without_owning_qr():
    routes = (ROOT / "frontend/desktop/modules/purchasing/enterprise_routes.py").read_text(
        encoding="utf-8")
    assert "LogisticsShipmentQueryService" in routes
    assert "QrTraceabilityReadService" not in routes
    assert "CompleteQrReceptionUseCase" not in routes
