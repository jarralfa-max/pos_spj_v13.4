# flows/base_flow.py — Base de la state machine
"""
Cada flow recibe el contexto y el mensaje parseado,
ejecuta la lógica del estado actual, y retorna el nuevo estado.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent
from erp.bridge import ERPBridge
from erp.events import WAEventEmitter

if TYPE_CHECKING:
    from erp.business_orchestrator import BusinessOrchestrator
    from state.reminder_engine import ReminderEngine


class FlowResult:
    """Resultado de procesar un paso del flow."""
    def __init__(self, new_state: FlowState = FlowState.IDLE,
                 handled: bool = True):
        self.new_state = new_state
        self.handled = handled


class BaseFlow:
    """
    Clase base para todos los flows.

    FASE WA: agrega orquestador y motor de recordatorios como opcionales
    para no romper flows existentes que no los usen.
    """

    def __init__(self, erp: ERPBridge, events: WAEventEmitter,
                 orchestrator: Optional["BusinessOrchestrator"] = None,
                 reminders: Optional["ReminderEngine"] = None):
        self.erp = erp
        self.events = events
        self.orchestrator = orchestrator    # BusinessOrchestrator (opcional)
        self.reminders = reminders          # ReminderEngine (opcional)

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:
        raise NotImplementedError
