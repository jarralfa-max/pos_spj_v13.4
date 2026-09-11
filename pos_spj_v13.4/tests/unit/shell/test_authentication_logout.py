"""Signing out delegates to the existing session lifecycle operation."""
from unittest.mock import Mock

from frontend.desktop.auth.authentication_coordinator import AuthenticationCoordinator


def test_logout_uses_injected_session_revocation():
    revoke = Mock()
    coordinator = AuthenticationCoordinator(
        installation_status_query=Mock(), setup_wizard_factory=Mock(),
        login_window_factory=Mock(), build_application_context=Mock(),
        on_authenticated=Mock(), revoke_session=revoke,
    )
    coordinator.logout("01992d31-54a0-7000-8000-000000000001")
    revoke.assert_called_once_with("01992d31-54a0-7000-8000-000000000001")
