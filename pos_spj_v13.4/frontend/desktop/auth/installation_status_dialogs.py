"""InstallationRecoveryRequiredDialog / InstallationLockedDialog — SHELL-7.

Deliberately minimal: `Installation.RECOVERY_REQUIRED`/`LOCKED` states exist
in the SHELL-2 domain model, but nothing in the app currently transitions
an installation into either state (no caller invokes
`Installation.lock()`/`.require_recovery()` yet), so these are informational
dead-ends today rather than full recovery-kit-code-redemption screens.
`AuthenticationCoordinator` still needs somewhere to route for these states
to be a complete, correct router — building the full
`InstallationRecoveryKit` code-redemption UI is separate, larger scope
(reusing SHELL-2's `InstallationRecoveryKit.redeem()`) for whenever
something actually produces these states.
"""
from __future__ import annotations

from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.themes.tokens import DialogMetrics


class InstallationLockedDialog(StandardDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Instalación bloqueada", width=DialogMetrics.WIDTH_SM)
        from PyQt5.QtWidgets import QLabel

        message = QLabel(
            "Esta instalación está bloqueada. Contacte al propietario del "
            "sistema o al soporte técnico para desbloquearla.",
            self,
        )
        message.setWordWrap(True)
        self.content_layout().addWidget(message)
        close_btn = create_primary_button(self, "Cerrar")
        close_btn.clicked.connect(self.reject)
        self.content_layout().addWidget(close_btn)


class InstallationRecoveryRequiredDialog(StandardDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Recuperación requerida", width=DialogMetrics.WIDTH_SM)
        from PyQt5.QtWidgets import QLabel

        message = QLabel(
            "Esta instalación requiere recuperación antes de poder continuar. "
            "Contacte al propietario del sistema o al soporte técnico.",
            self,
        )
        message.setWordWrap(True)
        self.content_layout().addWidget(message)
        close_btn = create_primary_button(self, "Cerrar")
        close_btn.clicked.connect(self.reject)
        self.content_layout().addWidget(close_btn)
