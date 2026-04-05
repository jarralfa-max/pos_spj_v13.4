# flows/repetir_flow.py — Repetir último pedido
"""
Busca el último pedido del cliente y permite repetirlo con un click.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState, PedidoItem
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from messaging.sender import send_text, send_buttons
from messaging import interactive


class RepetirFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        if not ctx.cliente_id:
            await send_text(ctx.phone,
                "No tengo un historial de pedidos para tu número.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        ultimo = self.erp.get_ultimo_pedido(ctx.cliente_id)
        if not ultimo:
            await send_text(ctx.phone,
                "No encontré pedidos anteriores. ¿Quieres hacer uno nuevo?")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        # Mostrar resumen del último pedido
        lines = [f"🔄 *Tu último pedido* ({ultimo['folio']}):\n"]
        for it in ultimo["items"]:
            lines.append(
                f"• {it['nombre']}: {it['cantidad']} {it.get('unidad','kg')} "
                f"— ${float(it['precio_unitario']) * float(it['cantidad']):.2f}")
        lines.append(f"\nTotal: *${ultimo['total']:.2f}*")

        await send_buttons(
            ctx.phone,
            body="\n".join(lines),
            buttons=[
                {"id": "confirm_repetir", "title": "✅ Repetir igual"},
                {"id": "menu_pedido", "title": "✏️ Modificar"},
                {"id": "cancel_ok", "title": "❌ Cancelar"},
            ])

        # Pre-cargar items en el contexto
        ctx.pedido_items = []
        for it in ultimo["items"]:
            ctx.pedido_items.append(PedidoItem(
                producto_id=it["producto_id"],
                nombre=it["nombre"],
                cantidad=float(it["cantidad"]),
                unidad=it.get("unidad", "kg"),
                precio_unitario=float(it["precio_unitario"]),
            ))

        return FlowResult(FlowState.PEDIDO_CONFIRMACION)
