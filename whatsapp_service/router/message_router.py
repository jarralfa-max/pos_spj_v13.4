# router/message_router.py — Orquestador principal de mensajes
"""
Recibe mensaje parseado → determina qué flow ejecutar → actualiza estado.

Orden de decisión:
1. ¿Número tipo notificaciones/interno? → ignorar o flujo especial
2. ¿Necesita seleccionar sucursal? → SucursalFlow
3. ¿Necesita registrarse? → RegistroFlow
4. ¿Está en medio de un flujo? → Continuar ese flow
5. ¿Es intención nueva? → Iniciar flow correspondiente
6. Fallback → MenuFlow
"""
from __future__ import annotations
import logging
from models.message import IncomingMessage
from models.context import ConversationContext, FlowState
from parser.intent_parser import IntentParser, ParsedIntent
from config.numbers import NumeroConfig, NumeroTipo
from config.schedules import ScheduleService
from state.conversation import ConversationStore
from erp.bridge import ERPBridge
from erp.events import WAEventEmitter
from flows.sucursal_flow import SucursalFlow
from flows.registro_flow import RegistroFlow
from flows.menu_flow import MenuFlow
from flows.pedido_flow import PedidoFlow
from flows.repetir_flow import RepetirFlow
from flows.cotizacion_flow import CotizacionFlow
from flows.pago_flow import PagoFlow
from messaging import interactive
from middleware.handoff import HandoffService

logger = logging.getLogger("wa.router")


class MessageRouter:
    def __init__(self, erp: ERPBridge, store: ConversationStore,
                 parser: IntentParser, events: WAEventEmitter,
                 schedules: ScheduleService, handoff: HandoffService):
        self.erp = erp
        self.store = store
        self.parser = parser
        self.events = events
        self.schedules = schedules
        self.handoff = handoff

        # Flows
        self.sucursal_flow = SucursalFlow(erp, events)
        self.registro_flow = RegistroFlow(erp, events)
        self.menu_flow = MenuFlow(erp, events)
        self.pedido_flow = PedidoFlow(erp, events)
        self.repetir_flow = RepetirFlow(erp, events)
        self.cotizacion_flow = CotizacionFlow(erp, events)
        self.pago_flow = PagoFlow(erp, events)

    async def route(self, msg: IncomingMessage, numero_cfg: NumeroConfig):
        """Punto de entrada principal — procesa un mensaje entrante."""

        # 1. Ignorar números de solo notificaciones
        if numero_cfg.tipo == NumeroTipo.NOTIFICACIONES:
            logger.debug("Mensaje ignorado: número solo notificaciones")
            return

        # 2. Cargar contexto de conversación
        ctx = self.store.get(msg.from_number)
        ctx.numero_tipo = numero_cfg.tipo.value
        ctx.last_activity = msg.timestamp

        # 3. ¿Número global sin sucursal? → forzar selección
        if numero_cfg.es_global and not ctx.sucursal_id:
            sucursales = self.erp.get_sucursales()
            await interactive.send_seleccion_sucursal(msg.from_number, sucursales)
            ctx.state = FlowState.SELECTING_BRANCH
            self.store.save(ctx)
            return

        # Si número tiene sucursal fija, asignarla
        if numero_cfg.sucursal_id and not ctx.sucursal_id:
            ctx.sucursal_id = numero_cfg.sucursal_id
            ctx.sucursal_nombre = numero_cfg.sucursal_nombre

        # 4. Parsear intención
        intent = await self.parser.parse(msg)
        logger.info("MSG %s → intent=%s, state=%s",
                     msg.from_number, intent.intent, ctx.state.value)

        # 5. ¿Cancelar en cualquier momento?
        if intent.intent == "cancel" and ctx.state != FlowState.IDLE:
            ctx.reset_flow()
            from messaging.sender import send_text
            await send_text(ctx.phone, "❌ Operación cancelada.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            self.store.save(ctx)
            return

        # 6. ¿Cliente registrado?
        if not ctx.cliente_id:
            cliente = self.erp.find_cliente_by_phone(msg.from_number)
            if cliente:
                ctx.cliente_id = cliente["id"]
                ctx.cliente_nombre = cliente["nombre"]
            elif ctx.state not in (FlowState.REGISTRO_NOMBRE,
                                    FlowState.REGISTRO_CONFIRMACION):
                await self.registro_flow.iniciar(ctx, msg.contact_name)
                self.store.save(ctx)
                return

        # 7. Router de estado → flow activo
        result = None

        # ── Selección de sucursal ─────────────────────────────────────
        if ctx.state == FlowState.SELECTING_BRANCH:
            result = await self.sucursal_flow.handle(ctx, intent)

        # ── Registro ──────────────────────────────────────────────────
        elif ctx.state in (FlowState.REGISTRO_NOMBRE,
                           FlowState.REGISTRO_CONFIRMACION):
            result = await self.registro_flow.handle(ctx, intent)

        # ── Pedido ────────────────────────────────────────────────────
        elif ctx.state.value.startswith("pedido_"):
            # Verificar horario
            if (ctx.state == FlowState.PEDIDO_CATEGORIA and
                    not self.schedules.esta_abierta(ctx.sucursal_id or 1)):
                proximo = self.schedules.proximo_horario_apertura(
                    ctx.sucursal_id or 1)
                await interactive.send_fuera_de_horario(
                    ctx.phone, proximo or "mañana")
                ctx.pedido_programado = True

            result = await self.pedido_flow.handle(ctx, intent)

        # ── Cotización ────────────────────────────────────────────────
        elif ctx.state.value.startswith("cotizacion_"):
            result = await self.cotizacion_flow.handle(ctx, intent)

        # ── Pago ──────────────────────────────────────────────────────
        elif ctx.state.value.startswith("pago_"):
            result = await self.pago_flow.handle(ctx, intent)

        # ── Consulta folio ────────────────────────────────────────────
        elif ctx.state == FlowState.CONSULTA_FOLIO:
            result = await self.menu_flow.handle(ctx, intent)

        # 8. Si ningún flow lo manejó → router de intención
        if result is None or not result.handled:
            # Intenciones que inician flows
            if intent.intent in ("pedido", "menu_action") and \
                    intent.action_id in ("menu_pedido", ""):
                ctx.state = FlowState.PEDIDO_CATEGORIA
                result = await self.pedido_flow.handle(ctx, intent)

            elif intent.intent == "repetir" or intent.action_id == "menu_repetir":
                result = await self.repetir_flow.handle(ctx, intent)

            elif intent.intent in ("cotizacion",) or \
                    intent.action_id == "menu_cotizacion":
                ctx.state = FlowState.COTIZACION_ARMANDO
                result = await self.cotizacion_flow.handle(ctx, intent)

            else:
                result = await self.menu_flow.handle(ctx, intent)

        # 9. Actualizar estado y guardar
        if result:
            ctx.state = result.new_state
        self.store.save(ctx)
