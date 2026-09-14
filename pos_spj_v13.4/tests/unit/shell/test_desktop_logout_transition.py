"""Logout revokes first, releases the old shell, and re-enters authentication."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from frontend.desktop.app import _logout_and_reauthenticate


@pytest.mark.parametrize("accepted", [True, False])
def test_logout_transition_restores_quit_policy_and_never_reuses_shell(accepted):
    events = []
    app = Mock()
    app.quitOnLastWindowClosed.return_value = True
    window = Mock()
    window.router.current_context = SimpleNamespace(session_id="session")
    window.hide.side_effect = lambda: events.append("hide")
    coordinator = Mock()
    coordinator.logout.side_effect = lambda _: events.append("revoke")
    coordinator.run.side_effect = lambda: events.append("login") or accepted
    assert _logout_and_reauthenticate(app, window, coordinator) is accepted
    assert events == ["revoke", "hide", "login"]
    window.setEnabled.assert_called_once_with(False)
    window.deleteLater.assert_called_once()
    assert app.setQuitOnLastWindowClosed.call_args_list[-1].args == (True,)
    assert app.quit.called is (not accepted)


def test_revocation_failure_keeps_current_session_visible(monkeypatch):
    app, window, coordinator = Mock(), Mock(), Mock()
    coordinator.logout.side_effect = RuntimeError("unavailable")
    report = Mock()
    monkeypatch.setattr("frontend.desktop.app.QMessageBox.critical", report)
    assert _logout_and_reauthenticate(app, window, coordinator) is False
    window.hide.assert_not_called()
    window.deleteLater.assert_not_called()
    coordinator.run.assert_not_called()
    report.assert_called_once()
