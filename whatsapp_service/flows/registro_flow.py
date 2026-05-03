# flows/registro_flow.py — Registro/vinculación de cliente
"""
Cuando un número desconocido escribe, se registra con datos mínimos.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from erp.events import WA_CLIENTE_REGISTRADO
from messaging.sender import send_text, send_buttons
from messaging import interactive


class RegistroFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        if ctx.state == FlowState.REGISTRO_NOMBRE:
            return await self._handle_nombre(ctx, intent)

        if ctx.state == FlowState.REGISTRO_CONFIRMACION:
            return await self._handle_confirmacion(ctx, intent)

        return FlowResult(handled=False)

    async def iniciar(self, ctx: ConversationContext,
                      contact_name: str = ""):
        """Inicia el flujo de registro para número desconocido."""
        if contact_name and len(contact_name) >= 2:
            # Usar nombre del perfil de WhatsApp
            await send_buttons(
                ctx.phone,
                body=f"👋 ¡Hola! No tenemos tu número registrado.\n"
                     f"¿Tu nombre es *{contact_name}*?",
                buttons=[
                    {"id": "confirm_nombre_si", "title": "✅ Sí, soy yo"},
                    {"id": "confirm_nombre_no", "title": "✏️ Otro nombre"},
                ])
            ctx._producto_temp = {"contact_name": contact_name}
            ctx.state = FlowState.REGISTRO_CONFIRMACION
        else:
            await send_text(ctx.phone,
                "👋 ¡Hola! No tenemos tu número registrado.\n"
                "¿Cómo te llamas?")
            ctx.state = FlowState.REGISTRO_NOMBRE

    async def _handle_nombre(self, ctx, intent):
        nombre = intent.raw_text.strip()
        if not nombre or len(nombre) < 2:
            await send_text(ctx.phone, "Escribe tu nombre completo:")
            return FlowResult(FlowState.REGISTRO_NOMBRE)

        return await self._registrar(ctx, nombre)

    async def _handle_confirmacion(self, ctx, intent):
        aid = intent.action_id

        if aid == "confirm_nombre_si":
            nombre = (ctx._producto_temp or {}).get("contact_name", "Cliente")
            return await self._registrar(ctx, nombre)

        if aid == "confirm_nombre_no":
            await send_text(ctx.phone, "¿Cómo te llamas?")
            return FlowResult(FlowState.REGISTRO_NOMBRE)

        # Texto libre = el nombre
        nombre = intent.raw_text.strip()
        if nombre and len(nombre) >= 2:
            return await self._registrar(ctx, nombre)

        await send_text(ctx.phone, "Escribe tu nombre:")
        return FlowResult(FlowState.REGISTRO_NOMBRE)

    async def _registrar(self, ctx, nombre):
        cliente_id = self.erp.create_cliente_minimo(nombre, ctx.phone)
        ctx.cliente_id = cliente_id
        ctx.cliente_nombre = nombre
        ctx._producto_temp = None

        self.events.emit(WA_CLIENTE_REGISTRADO, {
            "cliente_id": cliente_id,
            "nombre": nombre,
            "telefono": ctx.phone,
        }, sucursal_id=ctx.sucursal_id or 1)

        await send_text(ctx.phone,
            f"✅ ¡Listo, *{nombre}*! Ya quedaste registrado.")
        await interactive.send_menu_principal(ctx.phone, nombre)
        return FlowResult(FlowState.IDLE)
