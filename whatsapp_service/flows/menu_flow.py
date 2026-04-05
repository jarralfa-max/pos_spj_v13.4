# flows/menu_flow.py — Menú principal y saludos
"""
Maneja: saludos, ayuda, menú, gracias, y unknown.
Es el flow por defecto cuando no hay flujo activo.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from messaging import interactive
from messaging.sender import send_text
from config.settings import MAX_FAILED_INTENTS


class MenuFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        i = intent.intent
        aid = intent.action_id

        # ── Botones del menú principal ────────────────────────────────────
        if aid == "menu_pedido":
            ctx.state = FlowState.PEDIDO_CATEGORIA
            return FlowResult(FlowState.PEDIDO_CATEGORIA, handled=False)

        if aid == "menu_cotizacion":
            ctx.state = FlowState.COTIZACION_ARMANDO
            return FlowResult(FlowState.COTIZACION_ARMANDO, handled=False)

        if aid == "menu_estado":
            await send_text(ctx.phone,
                "Escribe el folio de tu pedido (ej: WA-A1B2C3D4):")
            return FlowResult(FlowState.CONSULTA_FOLIO)

        if aid == "menu_repetir":
            return FlowResult(FlowState.IDLE, handled=False)

        if aid == "menu_sucursal":
            sucursales = self.erp.get_sucursales()
            await interactive.send_seleccion_sucursal(ctx.phone, sucursales)
            return FlowResult(FlowState.SELECTING_BRANCH)

        if aid == "menu_ayuda":
            await self._send_ayuda(ctx.phone)
            return FlowResult(FlowState.IDLE)

        # ── Intenciones por texto ─────────────────────────────────────────
        if i in ("saludo", "ayuda"):
            await interactive.send_menu_principal(
                ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        if i == "gracias":
            await send_text(ctx.phone,
                "¡Con gusto! 😊 ¿Necesitas algo más?")
            return FlowResult(FlowState.IDLE)

        if i == "pedido":
            ctx.state = FlowState.PEDIDO_CATEGORIA
            return FlowResult(FlowState.PEDIDO_CATEGORIA, handled=False)

        if i == "cotizacion":
            ctx.state = FlowState.COTIZACION_ARMANDO
            return FlowResult(FlowState.COTIZACION_ARMANDO, handled=False)

        if i == "repetir":
            return FlowResult(FlowState.IDLE, handled=False)

        if i == "estado_pedido":
            await send_text(ctx.phone,
                "Escribe el folio de tu pedido (ej: WA-A1B2C3D4):")
            return FlowResult(FlowState.CONSULTA_FOLIO)

        if i == "cancelar":
            ctx.reset_flow()
            await send_text(ctx.phone, "Operación cancelada.")
            await interactive.send_menu_principal(
                ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        if i == "sucursal":
            sucursales = self.erp.get_sucursales()
            await interactive.send_seleccion_sucursal(ctx.phone, sucursales)
            return FlowResult(FlowState.SELECTING_BRANCH)

        if i == "pago":
            await send_text(ctx.phone,
                "Para pagar, necesito el folio de tu pedido:")
            return FlowResult(FlowState.CONSULTA_FOLIO)

        # ── Consulta de folio ─────────────────────────────────────────────
        if ctx.state == FlowState.CONSULTA_FOLIO:
            return await self._handle_consulta_folio(ctx, intent)

        # ── No entendí ────────────────────────────────────────────────────
        ctx.failed_intents += 1
        if ctx.failed_intents >= MAX_FAILED_INTENTS:
            ctx.failed_intents = 0
            await interactive.send_no_entendi(ctx.phone, intentos=3)
        else:
            await interactive.send_no_entendi(ctx.phone, ctx.failed_intents)
        return FlowResult(FlowState.IDLE)

    async def _handle_consulta_folio(self, ctx, intent):
        folio = intent.raw_text.strip().upper()
        if not folio:
            await send_text(ctx.phone, "Escribe el folio de tu pedido:")
            return FlowResult(FlowState.CONSULTA_FOLIO)

        resultado = self.erp.get_estado_pedido(folio)
        if resultado:
            estados_emoji = {
                "pendiente_wa": "⏳ Pendiente",
                "pendiente": "⏳ Pendiente",
                "confirmado": "✅ Confirmado",
                "en_preparacion": "👨‍🍳 En preparación",
                "listo": "📦 Listo para recoger",
                "en_camino": "🛵 En camino",
                "entregado": "✅ Entregado",
                "cancelada": "❌ Cancelado",
            }
            estado_txt = estados_emoji.get(
                resultado["estado"], resultado["estado"])
            await send_text(ctx.phone,
                f"📦 Pedido *{resultado['folio']}*\n"
                f"Estado: {estado_txt}\n"
                f"Total: ${float(resultado['total']):.2f}\n"
                f"Fecha: {resultado['fecha']}")
        else:
            await send_text(ctx.phone,
                f"No encontré un pedido con folio '{folio}'.\n"
                f"Verifica el folio e intenta de nuevo.")

        await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
        return FlowResult(FlowState.IDLE)

    async def _send_ayuda(self, to):
        await send_text(to,
            "📖 *Ayuda — SPJ POS WhatsApp*\n\n"
            "Puedo ayudarte con:\n"
            "• 🛒 *Hacer pedido* — arma tu pedido paso a paso\n"
            "• 📋 *Cotización* — consulta precios sin compromiso\n"
            "• 🔄 *Repetir pedido* — repite tu último pedido\n"
            "• 📦 *Estado de pedido* — rastrea tu pedido con el folio\n"
            "• 📍 *Cambiar sucursal* — cambia tu sucursal\n\n"
            "Escribe cualquier opción o usa los botones. 👇")
