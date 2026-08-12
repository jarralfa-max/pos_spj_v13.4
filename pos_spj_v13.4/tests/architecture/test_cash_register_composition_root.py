from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cash_module_loader_uses_canonical_factory():
    loader = (ROOT / "core/ui/module_loader.py").read_text(encoding="utf-8")
    assert '"caja":             ("CashRegisterModuleHost"' in loader
    assert "backend.infrastructure.desktop.cash_register_factory" in loader
    assert "modulos.caja" not in loader
    assert "ModuloCaja" not in loader


def test_main_window_uses_cash_register_host_not_legacy_workspace_alias():
    source = (ROOT / "interfaz/main_window.py").read_text(encoding="utf-8")
    assert "CashRegisterModuleHost" in source
    assert "CashRegisterWorkspace as ModuloCaja" not in source
    assert "ModuloCaja" not in source


def test_cash_factory_is_only_layer_that_receives_composition_root():
    factory = (
        ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
    ).read_text(encoding="utf-8")
    assert "class CashRegisterModuleHost" in factory
    assert "build_cash_register_presenter" in factory
    assert "create_cash_register_view" in factory
    assert "CashRegisterWorkspace(presenter=" in factory


def test_cash_frontend_does_not_receive_appcontainer_or_use_service_locator():
    frontend_files = [
        ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py",
        ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py",
    ]
    forbidden = ("container", "AppContainer", "getattr(self._container", "getattr(container")
    offenders = []
    for path in frontend_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert not offenders, "\n".join(offenders)
