"""AuthenticationCoordinator — SHELL-7 UI tests.

Uses fake dialogs (plain objects with `.exec_()` returning a canned
`QDialog.Accepted`/`Rejected`) rather than real `QDialog` subclasses —
calling `.exec_()` on a real, unshown `QDialog` enters an actual modal
event loop and blocks forever in a headless test, since nothing will ever
close it. Real `LoginWindow`/`InitialSetupWizard` construction and login
logic are already covered end-to-end in their own test files; this file
only tests the coordinator's routing decisions.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from backend.security.provisioning.installation import ProvisioningStatus  # noqa: E402
from frontend.desktop.auth.authentication_coordinator import AuthenticationCoordinator  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


class FakeStatusQuery:
    def __init__(self, status):
        self._status = status

    def current_status(self):
        return self._status


class SequenceStatusQuery:
    def __init__(self, sequence):
        self._sequence = list(sequence)

    def current_status(self):
        return self._sequence.pop(0)


class FakeDialog:
    def __init__(self, result=QDialog.Accepted):
        self._result = result
        self.exec_calls = 0

    def exec_(self):
        self.exec_calls += 1
        return self._result


class FakeLoginWindow(FakeDialog):
    def __init__(self, result=QDialog.Accepted, auth_result=None):
        super().__init__(result)
        self.authentication_result = auth_result


def _coordinator(app, *, status, on_authenticated=None, **overrides):
    kwargs = dict(
        installation_status_query=FakeStatusQuery(status),
        setup_wizard_factory=lambda: FakeDialog(),
        login_window_factory=lambda: FakeLoginWindow(auth_result="AUTH_RESULT"),
        build_application_context=lambda auth: f"CTX[{auth}]",
        on_authenticated=on_authenticated or (lambda ctx: None),
    )
    kwargs.update(overrides)
    return AuthenticationCoordinator(**kwargs)


def test_provisioned_with_successful_login_invokes_on_authenticated(app):
    captured = {}
    coordinator = _coordinator(
        app, status=ProvisioningStatus.PROVISIONED, on_authenticated=lambda ctx: captured.setdefault("ctx", ctx),
    )
    assert coordinator.run() is True
    assert captured["ctx"] == "CTX[AUTH_RESULT]"


def test_provisioned_with_cancelled_login_returns_false(app):
    captured = {}
    coordinator = _coordinator(
        app, status=ProvisioningStatus.PROVISIONED,
        login_window_factory=lambda: FakeLoginWindow(result=QDialog.Rejected),
        on_authenticated=lambda ctx: captured.setdefault("ctx", ctx),
    )
    assert coordinator.run() is False
    assert "ctx" not in captured


def test_uninitialized_shows_setup_wizard(app):
    wizard = FakeDialog(result=QDialog.Rejected)
    coordinator = _coordinator(
        app, status=ProvisioningStatus.UNINITIALIZED, setup_wizard_factory=lambda: wizard,
    )
    assert coordinator.run() is False
    assert wizard.exec_calls == 1


def test_uninitialized_then_provisioned_falls_through_to_login(app):
    captured = {}
    coordinator = _coordinator(
        app,
        status=None,  # unused, overridden below
        on_authenticated=lambda ctx: captured.setdefault("ctx", ctx),
    )
    coordinator._installation_status_query = SequenceStatusQuery(
        [ProvisioningStatus.UNINITIALIZED, ProvisioningStatus.PROVISIONED]
    )
    coordinator._setup_wizard_factory = lambda: FakeDialog(result=QDialog.Accepted)
    assert coordinator.run() is True
    assert captured["ctx"] == "CTX[AUTH_RESULT]"


def test_provisioning_in_progress_routes_to_wizard_same_as_uninitialized(app):
    wizard = FakeDialog(result=QDialog.Rejected)
    coordinator = _coordinator(
        app, status=ProvisioningStatus.PROVISIONING, setup_wizard_factory=lambda: wizard,
    )
    assert coordinator.run() is False
    assert wizard.exec_calls == 1


def test_locked_shows_locked_dialog_and_returns_false(app):
    locked_dialog = FakeDialog()
    coordinator = _coordinator(
        app, status=ProvisioningStatus.LOCKED, locked_dialog_factory=lambda: locked_dialog,
    )
    assert coordinator.run() is False
    assert locked_dialog.exec_calls == 1


def test_locked_without_dialog_factory_still_returns_false_safely(app):
    coordinator = _coordinator(app, status=ProvisioningStatus.LOCKED)
    assert coordinator.run() is False


def test_recovery_required_shows_recovery_dialog_and_returns_false(app):
    recovery_dialog = FakeDialog()
    coordinator = _coordinator(
        app, status=ProvisioningStatus.RECOVERY_REQUIRED,
        recovery_required_dialog_factory=lambda: recovery_dialog,
    )
    assert coordinator.run() is False
    assert recovery_dialog.exec_calls == 1


def test_login_window_accepted_but_no_authentication_result_returns_false(app):
    # defensive: LoginWindow.accept() should never be reachable without a
    # result, but the coordinator must not crash if it somehow happens.
    captured = {}
    coordinator = _coordinator(
        app, status=ProvisioningStatus.PROVISIONED,
        login_window_factory=lambda: FakeLoginWindow(result=QDialog.Accepted, auth_result=None),
        on_authenticated=lambda ctx: captured.setdefault("ctx", ctx),
    )
    assert coordinator.run() is False
    assert "ctx" not in captured
