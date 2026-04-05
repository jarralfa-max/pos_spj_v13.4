# flows/pedido_flow.py — Flujo de pedido completo
"""
State machine: categoría → producto → cantidad → ¿más? → entrega → confirmar
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState, PedidoItem
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from erp.events import WA_PEDIDO_CREADO, WA_ANTICIPO_REQUERIDO
from messaging import interactive
from messaging.sender import send_text


class PedidoFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        state = ctx.state

        # ── INICIO: Mostrar categorías ────────────────────────────────────
        if state in (FlowState.IDLE, FlowState.PEDIDO_CATEGORIA):
            return await self._handle_categoria(ctx, intent)

        # ── Selección de producto ─────────────────────────────────────────
        if state == FlowState.PEDIDO_PRODUCTO:
            return await self._handle_producto(ctx, intent)

        # ── Cantidad ──────────────────────────────────────────────────────
        if state == FlowState.PEDIDO_CANTIDAD:
            return await self._handle_cantidad(ctx, intent)

        # ── ¿Agregar más? ────────────────────────────────────────────────
        if state == FlowState.PEDIDO_MAS_PRODUCTOS:
            return await self._handle_mas(ctx, intent)

        # ── Tipo de entrega ───────────────────────────────────────────────
        if state == FlowState.PEDIDO_TIPO_ENTREGA:
            return await self._handle_entrega(ctx, intent)

        # ── Dirección ─────────────────────────────────────────────────────
        if state == FlowState.PEDIDO_DIRECCION:
            return await self._handle_direccion(ctx, intent)

        # ── Confirmación ──────────────────────────────────────────────────
        if state == FlowState.PEDIDO_CONFIRMACION:
            return await self._handle_confirmacion(ctx, intent)

        return FlowResult(handled=False)

    # ── Handlers internos ─────────────────────────────────────────────────────

    async def _handle_categoria(self, ctx, intent):
        # Si viene de botón de categoría
        if intent.intent == "select_category" and intent.action_id:
            cat_name = intent.action_id.replace("cat_", "").replace("_", " ")
            productos = self.erp.get_productos_by_category(
                cat_name, ctx.sucursal_id)
            if productos:
                await interactive.send_productos(
                    ctx.phone, productos, cat_name)
                return FlowResult(FlowState.PEDIDO_PRODUCTO)
            else:
                await send_text(ctx.phone,
                    f"No hay productos disponibles en '{cat_name}'.")

        # Si trae productos extraídos del texto libre
        if intent.products:
            for prod in intent.products:
                item = PedidoItem(
                    producto_id=prod["id"],
                    nombre=prod["nombre"],
                    cantidad=prod["cantidad_solicitada"],
                    unidad=prod.get("unidad", "kg"),
                    precio_unitario=prod.get("precio", 0),
                )
                ctx.pedido_items.append(item)
            await interactive.send_mas_productos(
                ctx.phone, ctx.resumen_pedido())
            return FlowResult(FlowState.PEDIDO_MAS_PRODUCTOS)

        # Mostrar categorías
        categorias = self.erp.get_categorias(ctx.sucursal_id)
        if categorias:
            await interactive.send_categorias(ctx.phone, categorias)
        else:
            await send_text(ctx.phone,
                "No hay categorías configuradas. Escribe el nombre del producto.")
        return FlowResult(FlowState.PEDIDO_CATEGORIA)

    async def _handle_producto(self, ctx, intent):
        if intent.intent == "select_product" and intent.action_id:
            # action_id = "prod_15"
            try:
                prod_id = int(intent.action_id.split("_", 1)[1])
                prod = self.erp.get_producto(prod_id, ctx.sucursal_id)
                if prod:
                    ctx._producto_temp = prod
                    await interactive.send_cantidad(
                        ctx.phone, prod["nombre"], prod.get("unidad", "kg"))
                    return FlowResult(FlowState.PEDIDO_CANTIDAD)
            except (ValueError, IndexError):
                pass

        # Texto libre: buscar producto
        if intent.raw_text:
            from parser.product_matcher import ProductMatcher
            matcher = ProductMatcher(self.erp.db, ctx.sucursal_id)
            results = matcher.search(intent.raw_text, max_results=5)
            if results:
                await interactive.send_productos(ctx.phone, results)
                return FlowResult(FlowState.PEDIDO_PRODUCTO)

        await send_text(ctx.phone, "No encontré ese producto. Intenta de nuevo:")
        return FlowResult(FlowState.PEDIDO_PRODUCTO)

    async def _handle_cantidad(self, ctx, intent):
        qty = 0.0

        # Botón de cantidad rápida: "qty_5"
        if intent.intent == "select_quantity" and intent.action_id:
            try:
                qty = float(intent.action_id.split("_", 1)[1])
            except (ValueError, IndexError):
                pass

        # Número escrito
        if not qty and intent.number > 0:
            qty = intent.number

        # Intentar parsear texto como número
        if not qty:
            try:
                qty = float(intent.raw_text.replace(",", ".").strip())
            except (ValueError, AttributeError):
                pass

        if qty <= 0:
            await send_text(ctx.phone,
                "Escribe la cantidad (ej: 2.5) o usa los botones:")
            return FlowResult(FlowState.PEDIDO_CANTIDAD)

        prod = ctx._producto_temp
        if not prod:
            await send_text(ctx.phone, "Error: selecciona un producto primero.")
            return FlowResult(FlowState.PEDIDO_CATEGORIA)

        # Verificar stock
        if prod.get("stock", 0) < qty:
            stock_disp = prod.get("stock", 0)
            await send_text(ctx.phone,
                f"⚠️ Solo hay *{stock_disp:.1f} {prod.get('unidad','kg')}* "
                f"de {prod['nombre']} disponibles.\n"
                f"Escribe una cantidad menor o escribe 0 para omitir:")
            return FlowResult(FlowState.PEDIDO_CANTIDAD)

        # Agregar al pedido
        item = PedidoItem(
            producto_id=prod["id"],
            nombre=prod["nombre"],
            cantidad=qty,
            unidad=prod.get("unidad", "kg"),
            precio_unitario=prod.get("precio", 0),
        )
        ctx.pedido_items.append(item)
        ctx._producto_temp = None

        # ¿Más productos?
        await interactive.send_mas_productos(
            ctx.phone, ctx.resumen_pedido())
        return FlowResult(FlowState.PEDIDO_MAS_PRODUCTOS)

    async def _handle_mas(self, ctx, intent):
        aid = intent.action_id

        if aid == "mas_agregar":
            categorias = self.erp.get_categorias(ctx.sucursal_id)
            if categorias:
                await interactive.send_categorias(ctx.phone, categorias)
            return FlowResult(FlowState.PEDIDO_CATEGORIA)

        if aid == "mas_confirmar":
            await interactive.send_tipo_entrega(ctx.phone)
            return FlowResult(FlowState.PEDIDO_TIPO_ENTREGA)

        if aid == "cancel_pedido":
            ctx.reset_flow()
            await send_text(ctx.phone, "❌ Pedido cancelado.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        # Si escribe producto directamente en este paso
        if intent.products:
            for prod in intent.products:
                item = PedidoItem(
                    producto_id=prod["id"], nombre=prod["nombre"],
                    cantidad=prod["cantidad_solicitada"],
                    unidad=prod.get("unidad", "kg"),
                    precio_unitario=prod.get("precio", 0))
                ctx.pedido_items.append(item)
            await interactive.send_mas_productos(
                ctx.phone, ctx.resumen_pedido())
            return FlowResult(FlowState.PEDIDO_MAS_PRODUCTOS)

        await interactive.send_mas_productos(
            ctx.phone, ctx.resumen_pedido())
        return FlowResult(FlowState.PEDIDO_MAS_PRODUCTOS)

    async def _handle_entrega(self, ctx, intent):
        aid = intent.action_id

        if aid == "entrega_sucursal":
            ctx.pedido_tipo_entrega = "sucursal"
            return await self._confirmar_pedido(ctx)

        if aid == "entrega_domicilio":
            ctx.pedido_tipo_entrega = "domicilio"
            await send_text(ctx.phone,
                "📍 Escribe tu dirección de entrega:")
            return FlowResult(FlowState.PEDIDO_DIRECCION)

        await interactive.send_tipo_entrega(ctx.phone)
        return FlowResult(FlowState.PEDIDO_TIPO_ENTREGA)

    async def _handle_direccion(self, ctx, intent):
        if intent.raw_text and len(intent.raw_text) >= 5:
            ctx.pedido_direccion = intent.raw_text
            return await self._confirmar_pedido(ctx)

        await send_text(ctx.phone,
            "La dirección es muy corta. Incluye calle, número y colonia:")
        return FlowResult(FlowState.PEDIDO_DIRECCION)

    async def _confirmar_pedido(self, ctx):
        """Muestra resumen final y botón de confirmar."""
        entrega_txt = (f"🏪 Recoger en {ctx.sucursal_nombre}"
                       if ctx.pedido_tipo_entrega == "sucursal"
                       else f"🛵 Envío a: {ctx.pedido_direccion}")
        resumen = (f"{ctx.resumen_pedido()}\n\n"
                   f"Entrega: {entrega_txt}")

        from messaging.sender import send_buttons
        await send_buttons(
            ctx.phone,
            body=f"📋 *Confirma tu pedido:*\n\n{resumen}",
            buttons=[
                {"id": "confirm_pedido", "title": "✅ Confirmar"},
                {"id": "cancel_pedido", "title": "❌ Cancelar"},
            ])
        return FlowResult(FlowState.PEDIDO_CONFIRMACION)

    async def _handle_confirmacion(self, ctx, intent):
        aid = intent.action_id

        if aid == "cancel_pedido":
            ctx.reset_flow()
            await send_text(ctx.phone, "❌ Pedido cancelado.")
            await interactive.send_menu_principal(ctx.phone, ctx.cliente_nombre)
            return FlowResult(FlowState.IDLE)

        if aid == "confirm_pedido":
            # Crear pedido en ERP
            items = [i.to_dict() for i in ctx.pedido_items]
            result = self.erp.crear_pedido_wa(
                items=items,
                cliente_id=ctx.cliente_id or 0,
                sucursal_id=ctx.sucursal_id or 1,
                tipo_entrega=ctx.pedido_tipo_entrega,
                direccion=ctx.pedido_direccion,
            )

            folio = result["folio"]
            total = result["total"]

            # Emitir evento
            self.events.emit(WA_PEDIDO_CREADO, {
                "folio": folio, "total": total,
                "cliente_id": ctx.cliente_id,
                "items_count": len(ctx.pedido_items),
                "tipo_entrega": ctx.pedido_tipo_entrega,
            }, sucursal_id=ctx.sucursal_id or 1, prioridad=3)

            # Verificar si requiere anticipo
            if self.erp.requiere_anticipo(
                    ctx.cliente_id or 0, total, ctx.pedido_programado):
                self.events.emit(WA_ANTICIPO_REQUERIDO, {
                    "folio": folio, "monto": total * 0.5,
                }, sucursal_id=ctx.sucursal_id or 1, prioridad=2)
                await send_text(ctx.phone,
                    f"⚠️ Este pedido requiere un anticipo del 50%: "
                    f"*${total * 0.5:.2f}*\n"
                    f"Te enviaremos el link de pago.")

            # Confirmar
            await interactive.send_confirmacion_pedido(
                ctx.phone, ctx.resumen_pedido(), folio)

            ctx.reset_flow()
            return FlowResult(FlowState.IDLE)

        return FlowResult(FlowState.PEDIDO_CONFIRMACION)
