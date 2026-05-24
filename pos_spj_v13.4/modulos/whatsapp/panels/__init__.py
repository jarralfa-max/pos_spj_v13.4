# modulos/whatsapp/panels/__init__.py
from modulos.whatsapp.panels.status_panel import StatusPanel
from modulos.whatsapp.panels.credentials_panel import CredentialsPanel
from modulos.whatsapp.panels.numbers_panel import NumbersPanel
from modulos.whatsapp.panels.policies_panel import PoliciesPanel
from modulos.whatsapp.panels.webhook_panel import WebhookPanel
from modulos.whatsapp.panels.history_panel import HistoryPanel
from modulos.whatsapp.panels.diagnostics_panel import DiagnosticsPanel
from modulos.whatsapp.panels.ai_intent_panel import AIIntentPanel

__all__ = [
    "StatusPanel",
    "CredentialsPanel",
    "NumbersPanel",
    "PoliciesPanel",
    "WebhookPanel",
    "HistoryPanel",
    "DiagnosticsPanel",
    "AIIntentPanel",
]
