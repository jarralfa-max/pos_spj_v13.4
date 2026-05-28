# router/message_router.py — Orquestador principal de mensajes
"""
Recibe mensaje parseado → determina qué flow ejecutar → actualiza estado.

Orden de decisión:
1. ¿Número tipo notificaciones/interno? → ignorar o flujo especial
2. ¿Respuesta a ajuste pendiente? → aplicar/rechazar ajuste delivery
3. ¿Necesita seleccionar sucursal? → SucursalFlow
4. ¿Necesita registrarse? → RegistroFlow
5. ¿Está en medio de un flujo? → Continuar ese flow
6. ¿Es intención nueva? → Iniciar flow correspondiente
7. Fallback → MenuFlow

Regla de cierre:
- Cancelar/terminar un pedido NO debe reenviar menú automáticamente.
- El cliente reabre conversación solo si manda una intención nueva explícita.
"""
from __future__ import annotations
import logging
from models.message import IncomingMessage
from models.context import FlowState
from parser.intent_parser import IntentParser
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
try:
    from whatsapp_service.ai.intent_resolver import IntentResolver
except Exception:  # pragma: no cover
    from ai.intent_resolver import IntentResolver

logger = logging.getLogger("wa.router")


class RouteContext:
    def __init__(self, router: "MessageRouter", msg: IncomingMessage, numero_cfg: NumeroConfig):
        self.router = router
        self.msg = msg
        self.numero_cfg = numero_cfg
        self.ctx = None
        self.intent = None
        self.handled = False


class MessageMiddleware:
    async def handle(self, rc: RouteContext) -> bool:
        return False


class NotificationNumberGuard(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        if rc.numero_cfg.tipo == NumeroTipo.NOTIFICACIONES:
            logger.debug("Mensaje ignorado: número solo notificaciones")
            return True
        return False


class AdjustmentResponseMiddleware(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        return await rc.router._handle_adjustment_response(rc.msg)


class BranchSelectionMiddleware(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        if rc.numero_cfg.es_global and not rc.ctx.sucursal_id:
            sucursales = rc.router.erp.get_sucursales()
            await interactive.send_seleccion_sucursal(rc.msg.from_number, sucursales)
            rc.ctx.state = FlowState.SELECTING_BRANCH
            rc.router.store.save(rc.ctx)
            return True
        if rc.numero_cfg.sucursal_id and not rc.ctx.sucursal_id:
            rc.ctx.sucursal_id = rc.numero_cfg.sucursal_id
            rc.ctx.sucursal_nombre = rc.numero_cfg.sucursal_nombre
        return False


class CancelFlowMiddleware(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        if rc.intent.intent in ("cancel", "cancelar") and rc.ctx.state != FlowState.IDLE:
            rc.ctx.reset_flow()
            from messaging.sender import send_text
            await send_text(rc.ctx.phone, "❌ Operación cancelada. Cuando quieras iniciar de nuevo, escribe *hola* o *pedido*.")
            rc.router.store.save(rc.ctx)
            return True
        return False


class CustomerIdentificationMiddleware(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        if rc.ctx.cliente_id:
            return False
        cliente = rc.router.erp.find_cliente_by_phone(rc.msg.from_number)
        if cliente:
            rc.ctx.cliente_id = cliente["id"]
            rc.ctx.cliente_nombre = cliente["nombre"]
            return False
        if rc.ctx.state not in (FlowState.REGISTRO_NOMBRE, FlowState.REGISTRO_CONFIRMACION):
            await rc.router.registro_flow.iniciar(rc.ctx, rc.msg.contact_name)
            rc.router.store.save(rc.ctx)
            return True
        return False


class MessagePipeline:
    def __init__(self, middlewares):
        self.middlewares = middlewares

    async def run(self, rc: RouteContext) -> bool:
        for mw in self.middlewares:
            if await mw.handle(rc):
                return True
        return False




class FlowRegistry:
    """Registro central para despacho de flows por estado e intención."""

    def __init__(self, router: "MessageRouter"):
        self.router = router

    async def dispatch_active_flow(self, ctx, intent):
        if ctx.state == FlowState.SELECTING_BRANCH:
            return await self.router.sucursal_flow.handle(ctx, intent)
        if ctx.state in (FlowState.REGISTRO_NOMBRE, FlowState.REGISTRO_CONFIRMACION):
            return await self.router.registro_flow.handle(ctx, intent)
        if ctx.state.value.startswith("pedido_"):
            if (ctx.state == FlowState.PEDIDO_CATEGORIA and
                    not self.router.schedules.esta_abierta(ctx.sucursal_id or 1)):
                proximo = self.router.schedules.proximo_horario_apertura(ctx.sucursal_id or 1)
                await interactive.send_fuera_de_horario(ctx.phone, proximo or "mañana")
                ctx.pedido_programado = True
            return await self.router.pedido_flow.handle(ctx, intent)
        if ctx.state.value.startswith("cotizacion_"):
            return await self.router.cotizacion_flow.handle(ctx, intent)
        if ctx.state.value.startswith("pago_"):
            return await self.router.pago_flow.handle(ctx, intent)
        if ctx.state == FlowState.CONSULTA_FOLIO:
            return await self.router.menu_flow.handle(ctx, intent)
        return None

    async def dispatch_new_intent_or_fallback(self, ctx, intent):
        if intent.intent in ("pedido", "menu_action") and intent.action_id in ("menu_pedido", ""):
            ctx.state = FlowState.PEDIDO_CATEGORIA
            return await self.router.pedido_flow.handle(ctx, intent)
        if intent.intent == "repetir" or intent.action_id == "menu_repetir":
            return await self.router.repetir_flow.handle(ctx, intent)
        if intent.intent in ("cotizacion",) or intent.action_id == "menu_cotizacion":
            ctx.state = FlowState.COTIZACION_ARMANDO
            return await self.router.cotizacion_flow.handle(ctx, intent)
        return await self.router.menu_flow.handle(ctx, intent)

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
        self.intent_resolver = IntentResolver(parser=parser, db=erp.db)

        self.sucursal_flow = SucursalFlow(erp, events)
        self.registro_flow = RegistroFlow(erp, events)
        self.menu_flow = MenuFlow(erp, events)
        self.pedido_flow = PedidoFlow(erp, events)
        self.repetir_flow = RepetirFlow(erp, events)
        self.cotizacion_flow = CotizacionFlow(erp, events)
        self.pago_flow = PagoFlow(erp, events)
        self.pipeline = MessagePipeline([
            NotificationNumberGuard(),
            AdjustmentResponseMiddleware(),
            BranchSelectionMiddleware(),
        ])
        self.post_intent_pipeline = MessagePipeline([
            CancelFlowMiddleware(),
            CustomerIdentificationMiddleware(),
        ])
        self.flow_registry = FlowRegistry(self)

    async def _handle_adjustment_response(self, msg: IncomingMessage) -> bool:
        raw = (msg.text or msg.interactive_title or "").strip().lower()
        if not raw:
            return False

        accept_tokens = ("aceptar ajuste", "acepto ajuste", "acepto", "aceptar", "si acepto", "sí acepto")
        reject_tokens = ("rechazar ajuste", "rechazo ajuste", "rechazo", "rechazar", "no acepto")
        accepted = None
        if any(t in raw for t in accept_tokens):
            accepted = True
        elif any(t in raw for t in reject_tokens):
            accepted = False
        else:
            return False

        try:
            from erp.adjustment_approval import AdjustmentApprovalService
            from messaging.sender import send_text
            svc = AdjustmentApprovalService(self.erp.db)
            if not svc.has_pending_for_phone(msg.from_number):
                return False
            result = svc.respond_latest_for_phone(msg.from_number, accepted=accepted)
            if not result.get("ok"):
                await send_text(msg.from_number, "No encontré ajustes pendientes para este número.")
                return True
            if accepted:
                await send_text(
                    msg.from_number,
                    f"✅ Ajuste aceptado para tu pedido *{result['folio']}*.\n"
                    f"Total actualizado: *${float(result['total']):.2f}*."
                )
            else:
                await send_text(
                    msg.from_number,
                    f"❌ Ajuste rechazado para tu pedido *{result['folio']}*.\n"
                    "Mantendremos el pedido con la cantidad original."
                )
            logger.info("Adjustment response phone=%s accepted=%s result=%s", msg.from_number, accepted, result)
            return True
        except Exception as exc:
            logger.error("Error procesando respuesta de ajuste: %s", exc, exc_info=True)
            return False

    async def route(self, msg: IncomingMessage, numero_cfg: NumeroConfig):
        """Punto de entrada principal — procesa un mensaje entrante."""
        rc = RouteContext(self, msg, numero_cfg)
        rc.ctx = self.store.get(msg.from_number)
        rc.ctx.numero_tipo = numero_cfg.tipo.value
        rc.ctx.last_activity = msg.timestamp

        if await self.pipeline.run(rc):
            return

        ctx = rc.ctx
        intent = await self.intent_resolver.resolve(msg, ctx)
        rc.intent = intent
        logger.info("MSG %s → intent=%s, state=%s",
                     msg.from_number, intent.intent, ctx.state.value)

        # Comando explícito para cambio de sucursal en número global.
        if intent.intent == "sucursal" and numero_cfg.es_global:
            sucursales = self.erp.get_sucursales()
            if ctx.sucursal_id:
                await interactive.send_text(
                    ctx.phone,
                    f"Sucursal actual: *{ctx.sucursal_nombre or ctx.sucursal_id}*.\n"
                    "Selecciona la sucursal a usar para este pedido."
                )
            await interactive.send_seleccion_sucursal(ctx.phone, sucursales)
            ctx.state = FlowState.SELECTING_BRANCH
            self.store.save(ctx)
            return

        if await self.post_intent_pipeline.run(rc):
            return

        result = await self.flow_registry.dispatch_active_flow(ctx, intent)

        if result is None or not result.handled:
            result = await self.flow_registry.dispatch_new_intent_or_fallback(ctx, intent)

        if result:
            ctx.state = result.new_state
        self.store.save(ctx)
