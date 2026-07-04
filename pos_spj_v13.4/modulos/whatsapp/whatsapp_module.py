# modulos/whatsapp/whatsapp_module.py
"""
Consola de administración WhatsApp Business — SPJ ERP v13.4

Panel de configuración, monitoreo, auditoría y diagnóstico.
No contiene lógica de negocio, no ejecuta SQL directo, no expone tokens.
"""
from __future__ import annotations

import logging

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from modulos.spj_styles import apply_object_names
from modulos.whatsapp.panels import (
    CredentialsPanel,
    DiagnosticsPanel,
    HistoryPanel,
    NumbersPanel,
    PoliciesPanel,
    StatusPanel,
    WebhookPanel,
    AIIntentPanel,
)
from core.services.whatsapp_admin_service import WhatsAppAdminService
from core.services.whatsapp_credential_service import WhatsAppCredentialService

logger = logging.getLogger("spj.ui.wa.module")

_REFRESH_INTERVAL_MS = 30_000


class ModuloWhatsApp(QWidget):
    """
    Módulo principal de administración WhatsApp.

    Tabs:
      1. Estado general       — métricas de conexión y actividad
      2. Meta / Credenciales  — tokens, phone_id, microservicio URL
      3. Números y canales    — CRUD de líneas WhatsApp por sucursal
      4. Políticas            — tabla de política de canales (solo lectura)
      5. Webhook              — control del servidor webhook local
      6. Historial            — búsqueda y auditoría de mensajes
      7. Diagnóstico          — pruebas de conectividad y log
    """

    def __init__(self, container, parent=None) -> None:
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = getattr(container, "sucursal_id", "") or ""
        self.usuario     = ""

        self._svc  = WhatsAppAdminService(container.db)
        self._cred = WhatsAppCredentialService(container.db)

        self._build_ui()
        apply_object_names(self)

        # Refresco suave — solo métricas/historial, sin bloquear la UI
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._soft_refresh)
        self._timer.start()

    # ── API pública (compatible con host del módulo) ───────────────────────────

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._soft_refresh()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root.addWidget(tabs)

        # ── Panel 1: Estado general ───────────────────────────────────────────
        self._panel_status = StatusPanel(self._svc)
        tabs.addTab(self._panel_status, "Estado")

        # ── Panel 2: Meta / Credenciales ─────────────────────────────────────
        self._panel_creds = CredentialsPanel(self._cred, self._svc)
        tabs.addTab(self._panel_creds, "Meta / Credenciales")

        # ── Panel 3: Números y canales ────────────────────────────────────────
        self._panel_numbers = NumbersPanel(self._svc, self._cred)
        tabs.addTab(self._panel_numbers, "Números y canales")

        # ── Panel 4: Políticas ────────────────────────────────────────────────
        tabs.addTab(PoliciesPanel(), "Políticas")

        # ── Panel 5: Webhook ──────────────────────────────────────────────────
        self._panel_webhook = WebhookPanel(
            self._svc, self._cred, container=self.container
        )
        tabs.addTab(self._panel_webhook, "Webhook")

        # ── Panel 6: Historial ────────────────────────────────────────────────
        self._panel_history = HistoryPanel(self._svc)
        tabs.addTab(self._panel_history, "Historial")

        # ── Panel 7: IA de intención ───────────────────────────────────────────
        self._panel_ai = AIIntentPanel(self._svc, self.container.db)
        tabs.addTab(self._panel_ai, "IA de intención")

        # ── Panel 8: Diagnóstico ──────────────────────────────────────────────
        self._panel_diag = DiagnosticsPanel(
            self._svc, self._cred, container=self.container
        )
        tabs.addTab(self._panel_diag, "Diagnóstico")

    # ── Refresco suave ────────────────────────────────────────────────────────

    def _soft_refresh(self) -> None:
        try:
            self._panel_status.refresh()
        except Exception as exc:
            logger.debug("_soft_refresh status: %s", exc)
        try:
            self._panel_history.refresh()
        except Exception as exc:
            logger.debug("_soft_refresh history: %s", exc)

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
