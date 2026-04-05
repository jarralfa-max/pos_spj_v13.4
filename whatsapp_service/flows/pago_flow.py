# flows/pago_flow.py — Flujo de pago y anticipos
"""
Maneja selección de método de pago y registro de anticipos.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from erp.events import WA_ANTICIPO_PAGADO
from messaging.sender import send_text, send_buttons
from messaging import interactive
from config.settings import MP_ACCESS_TOKEN


class PagoFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        state = ctx.state

        if state == FlowState.PAGO_METODO:
            return await self._handle_metodo(ctx, intent)

        if state == FlowState.PAGO_ESPERANDO:
            return await self._handle_esperando(ctx, intent)

        return FlowResult(handled=False)

    async def iniciar_pago(self, ctx: ConversationContext, total: float):
        """Inicia el flujo de selección de método de pago."""
        await interactive.send_metodo_pago(ctx.phone, total)
        ctx.state = FlowState.PAGO_METODO

    async def _handle_metodo(self, ctx, intent):
        aid = intent.action_id

        if aid == "pago_efectivo":
            await send_text(ctx.phone,
                "💵 Pagarás en efectivo al momento de recibir.\n"
                "Tu pedido queda confirmado. ✅")
            return FlowResult(FlowState.IDLE)

        if aid == "pago_link":
            link = await self._generar_link_pago(ctx)
            if link:
                await send_text(ctx.phone,
                    f"💳 Paga con este link:\n{link}\n\n"
                    f"Te avisaremos cuando confirmemos tu pago.")
            else:
                await send_text(ctx.phone,
                    "⚠️ No pudimos generar el link de pago.\n"
                    "Contacta a la sucursal directamente.")
            return FlowResult(FlowState.PAGO_ESPERANDO)

        if aid == "pago_terminal":
            await send_text(ctx.phone,
                "💳 Pagarás con terminal al recoger/recibir.\n"
                "Tu pedido queda confirmado. ✅")
            return FlowResult(FlowState.IDLE)

        await interactive.send_metodo_pago(ctx.phone, ctx.total_pedido())
        return FlowResult(FlowState.PAGO_METODO)

    async def _handle_esperando(self, ctx, intent):
        """Esperando confirmación de pago (MercadoPago webhook lo confirma)."""
        await send_text(ctx.phone,
            "⏳ Aún estamos esperando la confirmación de tu pago.\n"
            "Si ya pagaste, espera un momento — se confirma automáticamente.")
        return FlowResult(FlowState.PAGO_ESPERANDO)

    async def _generar_link_pago(self, ctx) -> str:
        """Genera link de pago de MercadoPago."""
        if not MP_ACCESS_TOKEN:
            return ""
        try:
            import httpx
            total = ctx.total_pedido()
            payload = {
                "items": [{
                    "title": f"Pedido SPJ POS",
                    "quantity": 1,
                    "unit_price": total,
                    "currency_id": "MXN",
                }],
                "back_urls": {
                    "success": "https://spjpos.com/pago/ok",
                    "failure": "https://spjpos.com/pago/error",
                },
                "auto_return": "approved",
                "external_reference": ctx.phone,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.mercadopago.com/checkout/preferences",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
                        "Content-Type": "application/json",
                    })
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return data.get("init_point", "")
        except Exception:
            pass
        return ""
