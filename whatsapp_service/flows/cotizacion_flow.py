# flows/cotizacion_flow.py — Flujo de cotización
"""
Mismo flujo que pedido pero crea cotización en vez de venta.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState, PedidoItem
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from erp.events import (
    WA_COTIZACION_CREADA,
    WHATSAPP_QUOTE_REJECTED,
    WHATSAPP_QUOTE_ACCEPTED,
    WHATSAPP_QUOTE_CONVERTED_TO_SALE,
)
from messaging import interactive
from messaging.sender import send_text, send_buttons


class CotizacionFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        state = ctx.state

        if state == FlowState.COTIZACION_ARMANDO:
            return await self._handle_armando(ctx, intent)

        if state == FlowState.COTIZACION_CONFIRMACION:
            return await self._handle_confirmacion(ctx, intent)

        return FlowResult(handled=False)

    async def _handle_armando(self, ctx, intent):
        # Reutilizar la lógica de selección de productos del PedidoFlow
        # pero guardando en cotizacion_items
        aid = intent.action_id

        if aid and aid.startswith("cat_"):
            cat_name = aid.replace("cat_", "").replace("_", " ")
            productos = self.erp.get_productos_by_category(
                cat_name, ctx.sucursal_id)
            if productos:
                await interactive.send_productos(ctx.phone, productos, cat_name)
            return FlowResult(FlowState.COTIZACION_ARMANDO)

        if aid and aid.startswith("prod_"):
            try:
                prod_id = int(aid.split("_", 1)[1])
                prod = self.erp.get_producto(prod_id, ctx.sucursal_id)
                if prod:
                    ctx._producto_temp = prod
                    await interactive.send_cantidad(
                        ctx.phone, prod["nombre"], prod.get("unidad", "kg"))
            except (ValueError, IndexError):
                pass
            return FlowResult(FlowState.COTIZACION_ARMANDO)

        if aid and aid.startswith("qty_"):
            try:
                qty = float(aid.split("_", 1)[1])
            except (ValueError, IndexError):
                qty = 0
            if qty > 0 and ctx._producto_temp:
                prod = ctx._producto_temp
                ctx.cotizacion_items.append(PedidoItem(
                    producto_id=prod["id"], nombre=prod["nombre"],
                    cantidad=qty, unidad=prod.get("unidad", "kg"),
                    precio_unitario=prod.get("precio", 0)))
                ctx._producto_temp = None

        # Número suelto = cantidad
        if intent.number > 0 and ctx._producto_temp:
            prod = ctx._producto_temp
            ctx.cotizacion_items.append(PedidoItem(
                producto_id=prod["id"], nombre=prod["nombre"],
                cantidad=intent.number, unidad=prod.get("unidad", "kg"),
                precio_unitario=prod.get("precio", 0)))
            ctx._producto_temp = None

        if aid == "mas_confirmar" or (ctx.cotizacion_items and aid == "mas_confirmar"):
            return await self._mostrar_confirmacion(ctx)

        if aid == "mas_agregar" or not ctx.cotizacion_items:
            categorias = self.erp.get_categorias(ctx.sucursal_id)
            if categorias:
                await interactive.send_categorias(ctx.phone, categorias)
            else:
                await send_text(ctx.phone, "Escribe el nombre del producto:")
            return FlowResult(FlowState.COTIZACION_ARMANDO)

        # Si hay items, mostrar resumen
        if ctx.cotizacion_items:
            total = sum(i.subtotal for i in ctx.cotizacion_items)
            lines = ["📋 *Tu cotización:*\n"]
            for it in ctx.cotizacion_items:
                lines.append(f"• {it.nombre}: {it.cantidad} {it.unidad} — ${it.subtotal:.2f}")
            lines.append(f"\n*Total estimado: ${total:.2f}*")
            await send_buttons(ctx.phone, body="\n".join(lines), buttons=[
                {"id": "mas_agregar", "title": "➕ Agregar más"},
                {"id": "mas_confirmar", "title": "✅ Solicitar"},
                {"id": "cancel_pedido", "title": "❌ Cancelar"},
            ])
            return FlowResult(FlowState.COTIZACION_ARMANDO)

        categorias = self.erp.get_categorias(ctx.sucursal_id)
        if categorias:
            await interactive.send_categorias(ctx.phone, categorias)
        return FlowResult(FlowState.COTIZACION_ARMANDO)

    async def _mostrar_confirmacion(self, ctx):
        total = sum(i.subtotal for i in ctx.cotizacion_items)
        lines = ["📋 *Confirmar cotización:*\n"]
        for it in ctx.cotizacion_items:
            lines.append(f"• {it.nombre}: {it.cantidad} {it.unidad} — ${it.subtotal:.2f}")
        lines.append(f"\n*Total: ${total:.2f}*")

        await send_buttons(ctx.phone, body="\n".join(lines), buttons=[
            {"id": "confirm_cotizacion", "title": "✅ Confirmar"},
            {"id": "cancel_pedido", "title": "❌ Cancelar"},
        ])
        return FlowResult(FlowState.COTIZACION_CONFIRMACION)

    async def _handle_confirmacion(self, ctx, intent):
        aid = intent.action_id

        if aid == "cancel_pedido":
            ctx.reset_flow()
            await send_text(ctx.phone, "❌ Cotización cancelada.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        if aid == "confirm_cotizacion":
            items = [i.to_dict() for i in ctx.cotizacion_items]
            suc_id = ctx.sucursal_id or 1

            # ── FASE WA: Usar orchestrator si disponible ──────────────────
            if self.orchestrator:
                result = self.orchestrator.confirmar_cotizacion(
                    cotizacion_id=0,   # se asigna internamente
                    cliente_id=ctx.cliente_id or 0,
                    items=items,
                )
                # Guardar cotizacion_id en contexto persistente para conversión posterior
                ctx.current_quote_id = result.get("cotizacion_id")
                ctx.current_quote_folio = result.get("folio", "")

                # Programar recordatorio de confirmación
                if self.reminders:
                    self.reminders.programar_confirmacion_pedido(
                        venta_id=result.get("cotizacion_id", 0),
                        folio=result["folio"],
                        phone=ctx.phone,
                        sucursal_id=suc_id,
                        delay_horas=24)
            else:
                result = self.erp.crear_cotizacion_wa(
                    items=items,
                    cliente_id=ctx.cliente_id or 0,
                    sucursal_id=suc_id)
                ctx.current_quote_id = result.get("cotizacion_id")
                ctx.current_quote_folio = result.get("folio", "")
                self.events.emit(WA_COTIZACION_CREADA, {
                    "folio": result["folio"],
                    "total": result["total"],
                    "cliente_id": ctx.cliente_id,
                }, sucursal_id=suc_id)

            await send_buttons(
                ctx.phone,
                body=(
                    f"✅ *Cotización generada*\n\n"
                    f"Folio: *{result['folio']}*\n"
                    f"Total estimado: *${result['total']:.2f}*\n\n"
                    "¿Qué deseas hacer ahora?"
                ),
                buttons=[
                    {"id": "quote_accept", "title": "✅ Aceptar cotización"},
                    {"id": "quote_modify", "title": "✏️ Modificar"},
                    {"id": "quote_reject", "title": "❌ Rechazar"},
                ],
            )
            return FlowResult(FlowState.COTIZACION_CONFIRMACION)

        if aid == "quote_modify":
            await send_text(ctx.phone, "✏️ Vamos a modificar la cotización. Agrega o ajusta productos.")
            categorias = self.erp.get_categorias(ctx.sucursal_id)
            if categorias:
                await interactive.send_categorias(ctx.phone, categorias)
            return FlowResult(FlowState.COTIZACION_ARMANDO)

        if aid == "quote_reject":
            quote_id = ctx.current_quote_id
            if quote_id:
                try:
                    self.erp.db.execute("UPDATE cotizaciones SET estado='rechazada' WHERE id=?", (quote_id,))
                    self.erp.db.commit()
                    self.events.emit(WHATSAPP_QUOTE_REJECTED, {
                        "quote_id": quote_id,
                        "quote_folio": ctx.current_quote_folio,
                        "customer_id": ctx.cliente_id,
                    }, sucursal_id=ctx.sucursal_id or 1)
                except Exception:
                    pass
            ctx.reset_flow()
            await send_text(ctx.phone, "❌ Cotización rechazada.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        if aid == "quote_accept":
            quote_id = ctx.current_quote_id
            if not quote_id:
                await send_text(ctx.phone, "No encontré una cotización activa para convertir.")
                return FlowResult(FlowState.IDLE)
            using_orchestrator = bool(self.orchestrator)
            result = self.orchestrator.convertir_cotizacion_a_venta(
                cotizacion_id=int(quote_id),
                cliente_id=ctx.cliente_id or 0,
            ) if using_orchestrator else self.erp.convertir_cotizacion_a_venta(int(quote_id))
            if not result:
                await send_text(ctx.phone, "La cotización ya no está vigente o no pudo convertirse.")
                return FlowResult(FlowState.COTIZACION_CONFIRMACION)
            if not using_orchestrator:
                self.events.emit(WHATSAPP_QUOTE_ACCEPTED, {
                    "quote_id": int(quote_id),
                    "quote_folio": ctx.current_quote_folio,
                    "customer_id": ctx.cliente_id,
                }, sucursal_id=ctx.sucursal_id or 1)
                self.events.emit(WHATSAPP_QUOTE_CONVERTED_TO_SALE, {
                    "quote_id": int(quote_id),
                    "quote_folio": ctx.current_quote_folio,
                    "sale_id": result.get("venta_id") or result.get("id"),
                    "sale_folio": result.get("folio"),
                    "customer_id": ctx.cliente_id,
                }, sucursal_id=ctx.sucursal_id or 1)
            await send_text(
                ctx.phone,
                f"✅ Cotización aceptada y convertida a venta.\nFolio venta: *{result.get('folio','')}*\nTotal: *${float(result.get('total',0)):.2f}*"
            )
            ctx.reset_flow()
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        return FlowResult(FlowState.COTIZACION_CONFIRMACION)
