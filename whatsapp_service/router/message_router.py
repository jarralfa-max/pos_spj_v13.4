# router/message_router.py — Orquestador principal de mensajes
"""
Recibe mensaje parseado → determina qué flow ejecutar → actualiza estado.

Orden de decisión:
1. ¿Número tipo notificaciones/interno? → ignorar o flujo especial
2. ¿Respuesta a ajuste pendiente? → aplicar/rechazar ajuste delivery
3. Resolver intención del mensaje
4. Si la intención requiere sucursal y no hay sucursal, pedirla y guardar intención pendiente
5. ¿Necesita registrarse? → RegistroFlow
6. ¿Está en medio de un flujo? → Continuar ese flow
7. ¿Es intención nueva? → Iniciar flow correspondiente
8. Fallback → MenuFlow

Regla de cierre:
- Cancelar/terminar un pedido NO debe reenviar menú automáticamente.
- El cliente reabre conversación solo si manda una intención nueva explícita.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

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


class NumberBranchAssignmentMiddleware(MessageMiddleware):
    """Asigna sucursal implícita solo cuando el número pertenece a una sucursal.

    Los números globales o números sin sucursal ya no bloquean antes de resolver
    intención. Primero entendemos qué quiere el cliente; si es pedido/cotización,
    entonces pedimos sucursal y continuamos el flujo original.
    """

    async def handle(self, rc: RouteContext) -> bool:
        if rc.numero_cfg.sucursal_id and not rc.ctx.sucursal_id:
            rc.ctx.sucursal_id = rc.numero_cfg.sucursal_id
            rc.ctx.sucursal_nombre = rc.numero_cfg.sucursal_nombre
        return False


class BranchSelectionMiddleware(MessageMiddleware):
    async def handle(self, rc: RouteContext) -> bool:
        if not rc.intent:
            return False
        if not rc.router._intent_requires_branch(rc.intent):
            return False
        if rc.ctx.sucursal_id:
            return False

        rc.router._store_pending_intent(rc.ctx, rc.intent)
        sucursales = rc.router.erp.get_sucursales()
        await interactive.send_seleccion_sucursal(rc.msg.from_number, sucursales)
        rc.ctx.state = FlowState.SELECTING_BRANCH
        rc.router.store.save(rc.ctx)
        return True


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
            return await self.router._handle_branch_selection(ctx, intent)
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
            if getattr(intent, "products", None):
                self.router._apply_intent_to_order_context(ctx, intent)
                await interactive.send_mas_productos(ctx.phone, ctx.resumen_pedido())
                return self.router._flow_result(FlowState.PEDIDO_MAS_PRODUCTOS)
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
        self.pre_intent_pipeline = MessagePipeline([
            NotificationNumberGuard(),
            AdjustmentResponseMiddleware(),
            NumberBranchAssignmentMiddleware(),
        ])
        self.post_intent_pipeline = MessagePipeline([
            BranchSelectionMiddleware(),
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

        if await self.pre_intent_pipeline.run(rc):
            return

        ctx = rc.ctx
        intent = await self.intent_resolver.resolve(msg, ctx)
        rc.intent = intent
        logger.info("MSG %s → intent=%s, state=%s, products=%d",
                    msg.from_number, intent.intent, ctx.state.value,
                    len(getattr(intent, "products", []) or []))

        # Comando explícito para cambio de sucursal.
        if intent.intent in ("sucursal", "change_branch"):
            sucursales = self.erp.get_sucursales()
            if ctx.sucursal_id:
                await interactive.send_text(
                    ctx.phone,
                    f"Sucursal actual: *{ctx.sucursal_nombre or ctx.sucursal_id}*.\n"
                    "Selecciona la sucursal a usar para este pedido."
                )
            self._store_pending_intent(ctx, intent)
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

    def _intent_requires_branch(self, intent) -> bool:
        return intent.intent in ("pedido", "cotizacion", "create_order", "create_quote", "schedule_order")

    def _store_pending_intent(self, ctx, intent) -> None:
        ctx._pending_intent = self._intent_to_payload(intent)

    def _pop_pending_intent(self, ctx):
        payload = getattr(ctx, "_pending_intent", None)
        ctx._pending_intent = None
        if not payload:
            return None
        try:
            from parser.intent_parser import ParsedIntent
            parsed = ParsedIntent(
                intent=payload.get("intent", "unknown"),
                confidence=float(payload.get("confidence", 1.0) or 1.0),
                action_id=payload.get("action_id", ""),
                products=payload.get("products", []),
                number=float(payload.get("number", 0.0) or 0.0),
                raw_text=payload.get("raw_text", ""),
                source=payload.get("source", "pending"),
            )
            for key, value in payload.get("extra", {}).items():
                setattr(parsed, key, value)
            return parsed
        except Exception:
            return None

    def _intent_to_payload(self, intent) -> Dict[str, Any]:
        base = {
            "intent": getattr(intent, "intent", "unknown"),
            "confidence": getattr(intent, "confidence", 1.0),
            "action_id": getattr(intent, "action_id", ""),
            "products": getattr(intent, "products", []) or [],
            "number": getattr(intent, "number", 0.0),
            "raw_text": getattr(intent, "raw_text", ""),
            "source": getattr(intent, "source", ""),
            "extra": {},
        }
        for attr in ("delivery_type", "scheduled_at", "branch_reference", "workflow_type", "needs_clarification", "clarification_question"):
            if hasattr(intent, attr):
                base["extra"][attr] = getattr(intent, attr)
        return base

    async def _handle_branch_selection(self, ctx, intent):
        result = await self.sucursal_flow.handle(ctx, intent)
        if result and result.handled and result.new_state == FlowState.IDLE:
            pending = self._pop_pending_intent(ctx)
            if pending and self._intent_requires_branch(pending):
                return await self.flow_registry.dispatch_new_intent_or_fallback(ctx, pending)
        return result

    def _apply_intent_to_order_context(self, ctx, intent) -> None:
        from models.context import PedidoItem

        for prod in getattr(intent, "products", []) or []:
            try:
                item = PedidoItem(
                    producto_id=int(prod["id"]),
                    nombre=prod["nombre"],
                    cantidad=float(prod.get("cantidad_solicitada", 1.0) or 1.0),
                    unidad=prod.get("unidad_solicitada") or prod.get("unidad", "kg"),
                    precio_unitario=float(prod.get("precio", 0.0) or 0.0),
                )
                ctx.pedido_items.append(item)
            except Exception as exc:
                logger.debug("Producto inválido ignorado en intención IA: %s (%s)", prod, exc)

        delivery_type = getattr(intent, "delivery_type", "") or ""
        if delivery_type in ("home_delivery", "domicilio"):
            ctx.pedido_tipo_entrega = "domicilio"
        elif delivery_type in ("pickup", "mostrador", "sucursal"):
            ctx.pedido_tipo_entrega = "sucursal"

        scheduled_at = getattr(intent, "scheduled_at", "") or ""
        if scheduled_at:
            ctx.pedido_fecha_entrega = scheduled_at
            ctx.pedido_programado = True

    def _flow_result(self, state: FlowState):
        from flows.base_flow import FlowResult
        return FlowResult(state)
