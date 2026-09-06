from unittest.mock import Mock

import pytest

from backend.bootstrap.installation_setup import ensure_installation_provisioned
from frontend.desktop.shell import desktop_shell_authentication_composition as composition


@pytest.mark.parametrize("ready", [True, False])
def test_bootstrap_uses_canonical_coordinator_without_starting_login(monkeypatch, ready):
    coordinator = Mock()
    coordinator.ensure_provisioned.return_value = ready
    factory = Mock(return_value=coordinator)
    monkeypatch.setattr(composition, "build_authentication_coordinator", factory)
    connection = object()

    assert ensure_installation_provisioned(connection) is ready
    assert factory.call_args.kwargs["connection"] is connection
    coordinator.ensure_provisioned.assert_called_once_with()
    coordinator.run.assert_not_called()
