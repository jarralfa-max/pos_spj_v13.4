"""Compose the canonical first-run coordinator before operational services start."""
from backend.bootstrap.composition_root import CompositionRoot
from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider


def ensure_installation_provisioned(connection) -> bool:
    from frontend.desktop.shell.desktop_shell_authentication_composition import build_authentication_coordinator

    services = CompositionRoot([SecurityModuleProvider()]).build()
    coordinator = build_authentication_coordinator(
        connection=connection, container=services, on_authenticated=lambda context: None,
    )
    return coordinator.ensure_provisioned()
