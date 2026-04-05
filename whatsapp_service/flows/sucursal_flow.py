# flows/sucursal_flow.py — Selección de sucursal
"""
Flujo obligatorio cuando el mensaje entra por número global
y el usuario no tiene sucursal asignada.
"""
from __future__ import annotations
from models.context import ConversationContext, FlowState
from parser.intent_parser import ParsedIntent
from flows.base_flow import BaseFlow, FlowResult
from messaging import interactive


class SucursalFlow(BaseFlow):

    async def handle(self, ctx: ConversationContext,
                     intent: ParsedIntent) -> FlowResult:

        # ── Respuesta a lista de sucursales ───────────────────────────────
        if intent.intent == "select_sucursal" and intent.action_id:
            # action_id = "suc_2" → sucursal_id = 2
            try:
                suc_id = int(intent.action_id.split("_", 1)[1])
                suc = self.erp.get_sucursal(suc_id)
                if suc:
                    ctx.sucursal_id = suc_id
                    ctx.sucursal_nombre = suc["nombre"]
                    await interactive.send_text(
                        ctx.phone,
                        f"✅ Sucursal *{suc['nombre']}* seleccionada.")
                    # Mostrar menú principal
                    await interactive.send_menu_principal(
                        ctx.phone, ctx.cliente_nombre)
                    return FlowResult(FlowState.IDLE)
            except (ValueError, IndexError):
                pass

        # ── Respuesta numérica ("1", "2", "3") ───────────────────────────
        from parser.patterns import extract_selection
        sel = extract_selection(intent.raw_text)
        if sel > 0:
            sucursales = self.erp.get_sucursales()
            if 1 <= sel <= len(sucursales):
                suc = sucursales[sel - 1]
                ctx.sucursal_id = suc["id"]
                ctx.sucursal_nombre = suc["nombre"]
                await interactive.send_text(
                    ctx.phone,
                    f"✅ Sucursal *{suc['nombre']}* seleccionada.")
                await interactive.send_menu_principal(
                    ctx.phone, ctx.cliente_nombre)
                return FlowResult(FlowState.IDLE)

        # ── Volver a mostrar lista ────────────────────────────────────────
        sucursales = self.erp.get_sucursales()
        await interactive.send_seleccion_sucursal(ctx.phone, sucursales)
        return FlowResult(FlowState.SELECTING_BRANCH)
