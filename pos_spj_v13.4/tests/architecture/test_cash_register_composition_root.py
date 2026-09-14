from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_shell_wires_cash_through_canonical_registration():
    """El cableado vivo de Caja, en positivo.

    Sustituye a dos pruebas que leían `core/ui/module_loader.py` e
    `interfaz/main_window.py`, borrados. Hoy el shell compone los módulos en
    `desktop_shell_window_composition.py`: registra el activador de Caja, y el
    activador construye la vista con `create_cash_register_view` de la factory
    canónica. La ausencia de `ModuloCaja`/`modulos.caja` en todo el runtime la
    fija `test_cash_legacy_removed.py`.
    """
    shell = (ROOT / "frontend/desktop/shell/desktop_shell_window_composition.py").read_text(encoding="utf-8")
    assert "from frontend.desktop.modules.cash_register.shell_registration import (" in shell
    assert "_standard_activator_factory(CashRegisterModuleActivator)" in shell

    registration = (ROOT / "frontend/desktop/modules/cash_register/shell_registration.py").read_text(encoding="utf-8")
    assert ("from backend.infrastructure.desktop.cash_register_factory import create_cash_register_view"
            in registration)
    assert "create_cash_register_view(_CashRegisterCompositionStandIn(" in registration


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
