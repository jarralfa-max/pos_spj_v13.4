
# rasa/actions/actions.py — SPJ POS v12
"""
Acciones personalizadas de Rasa que conectan el bot con la BD del POS.
Ejecutar con: rasa run actions --port 5055
"""
from __future__ import annotations
import os, sys, json, sqlite3, logging
from typing import Any, Text, Dict, List

# Intentar importar Rasa SDK; si no está disponible, definir stubs
try:
    from rasa_sdk import Action, Tracker, FormValidationAction
    from rasa_sdk.executor import CollectingDispatcher
    from rasa_sdk.events import SlotSet, AllSlotsReset
    _RASA_OK = True
except ImportError:
    _RASA_OK = False
    # Stubs para que el archivo sea importable sin Rasa instalado
    class Action:
        def name(self): return ""
        def run(self, d, t, e): return []
    class FormValidationAction(Action): pass
    class CollectingDispatcher:
        def utter_message(self, **kw): pass
    class Tracker:
        def get_slot(self, k): return None
        sender_id = ""
    def SlotSet(k, v): return {}
    def AllSlotsReset(): return {}

logger = logging.getLogger("spj.rasa.actions")

# Ruta a la BD del POS (configurable via variable de entorno)
DB_PATH = os.environ.get("SPJ_DB_PATH", "data/spj.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _buscar_cliente(numero: str) -> dict | None:
    try:
        conn = _get_conn()
        row  = conn.execute(
            "SELECT id, nombre, puntos FROM clientes WHERE telefono=? AND activo=1",
            (numero,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _buscar_producto(texto: str) -> dict | None:
    try:
        conn = _get_conn()
        words = texto.lower().split()
        for w in words:
            if len(w) < 3: continue
            row = conn.execute(
                "SELECT id, nombre, precio FROM productos "
                "WHERE LOWER(nombre) LIKE ? AND activo=1 LIMIT 1",
                (f"%{w}%",)).fetchone()
            if row:
                conn.close()
                return {"id": row[0], "nombre": row[1], "precio": float(row[2])}
        conn.close()
        return None
    except Exception:
        return None


# ── Acción: Bienvenida personalizada ─────────────────────────────────
class ActionBienvenidaPersonalizada(Action):
    def name(self) -> Text:
        return "action_bienvenida_personalizada"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero  = tracker.sender_id
        cliente = _buscar_cliente(numero)
        if cliente:
            puntos = cliente.get("puntos", 0)
            nombre = cliente["nombre"].split()[0]
            msg = (f"Hola *{nombre}* 👋\n"
                   f"Bienvenido de nuevo a *SPJ Pollos y Carnes*.\n\n")
            if puntos:
                msg += f"Tienes *{puntos} puntos* acumulados. 🎯\n\n"
            msg += ("¿Qué deseas hoy?\n"
                    "Escribe tu pedido (_1kg pechuga_) o *MENU* para ver productos.")
            dispatcher.utter_message(text=msg)
            return [SlotSet("nombre_cliente", nombre),
                    SlotSet("puntos_cliente", float(puntos))]
        else:
            dispatcher.utter_message(response="utter_bienvenida_sin_nombre")
            return []


# ── Acción: Procesar pedido (parsear items del texto) ─────────────────
class ActionProcesarPedido(Action):
    def name(self) -> Text:
        return "action_procesar_pedido"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        import re
        texto = tracker.latest_message.get("text", "")
        RE    = re.compile(
            r"(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|gramos?|g|piezas?|pz)?"\
            r"\s*(?:de\s+)?([a-záéíóúñü\s]+)",
            re.IGNORECASE | re.UNICODE)
        matches = RE.findall(texto)
        items   = []
        for qty_str, prod_txt in matches:
            qty  = float(qty_str.replace(",", "."))
            prod = _buscar_producto(prod_txt.strip())
            if prod:
                sub = round(qty * prod["precio"], 2)
                items.append({
                    "producto_id":     prod["id"],
                    "nombre_producto": prod["nombre"],
                    "cantidad":        qty,
                    "precio_unitario": prod["precio"],
                    "subtotal":        sub,
                })
        if not items:
            dispatcher.utter_message(
                text="No encontré productos en tu mensaje. 😅\n"
                     "Escríbelo así: _1kg pechuga, 2kg pierna_\n"
                     "o *MENU* para ver productos disponibles.")
            return []

        total   = sum(i["subtotal"] for i in items)
        detalle = "\n".join(
            f"• {i['cantidad']:.2f}kg {i['nombre_producto']} — ${i['subtotal']:.2f}"
            for i in items)
        msg = (f"🛒 *¿Confirmas tu pedido?*\n\n"
               f"{detalle}\n\n"
               f"💰 Total estimado: *${total:.2f}*\n\n"
               "Responde *sí* para confirmar o *no* para modificar.")
        dispatcher.utter_message(text=msg)
        return [SlotSet("items_pedido", items)]


# ── Acción: Crear pedido en BD ────────────────────────────────────────
class ActionCrearPedidoBD(Action):
    def name(self) -> Text:
        return "action_crear_pedido_bd"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero = tracker.sender_id
        items  = tracker.get_slot("items_pedido") or []
        if not items:
            dispatcher.utter_message(text="No tengo tu pedido. Escríbelo de nuevo.")
            return []
        total    = sum(float(i.get("subtotal", 0)) for i in items)
        cliente  = _buscar_cliente(numero)
        nombre_c = cliente["nombre"] if cliente else numero
        try:
            conn = _get_conn()
            pid  = conn.execute("""
                INSERT INTO pedidos_whatsapp
                (uuid, numero_whatsapp, cliente_id, cliente_nombre,
                 estado, subtotal, total, leido, fecha)
                VALUES(lower(hex(randomblob(16))),?,?,?,'nuevo',?,?,0,datetime('now'))""",
                (numero,
                 cliente["id"] if cliente else None,
                 nombre_c, total, total)).lastrowid
            for item in items:
                conn.execute("""
                    INSERT INTO pedidos_whatsapp_items
                    (pedido_id,producto_id,nombre_producto,
                     cantidad_pedida,precio_unitario,subtotal,unidad)
                    VALUES(?,?,?,?,?,?,'kg')""",
                    (pid, item["producto_id"], item["nombre_producto"],
                     item["cantidad"], item["precio_unitario"], item["subtotal"]))
            conn.commit()
            conn.close()
            dispatcher.utter_message(
                text=f"✅ *Pedido #{pid} recibido*\n\n"
                     "⚖️ Estamos pesando tus productos.\n"
                     "¿Cómo deseas recibirlo?\n\n"
                     "1️⃣ Recoger en mostrador\n"
                     "2️⃣ Envío a domicilio")
            return [SlotSet("pedido_id", str(pid))]
        except Exception as e:
            logger.error("crear pedido BD: %s", e)
            dispatcher.utter_message(
                text="Hubo un error al registrar tu pedido. Intenta de nuevo.")
            return []


# ── Acción: Confirmar pedido (entrega + pago listos) ──────────────────
class ActionConfirmarPedido(Action):
    def name(self) -> Text:
        return "action_confirmar_pedido"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        pid          = tracker.get_slot("pedido_id")
        tipo_entrega = tracker.get_slot("tipo_entrega") or "mostrador"
        forma_pago   = tracker.get_slot("forma_pago")   or "efectivo"
        direccion    = tracker.get_slot("direccion_entrega")
        try:
            conn = _get_conn()
            conn.execute("""
                UPDATE pedidos_whatsapp
                SET tipo_entrega=?, forma_pago=?, direccion_entrega=?,
                    estado='confirmado', fecha_confirmacion=datetime('now')
                WHERE id=?""",
                (tipo_entrega, forma_pago, direccion, pid))
            row = conn.execute(
                "SELECT total FROM pedidos_whatsapp WHERE id=?", (pid,)).fetchone()
            total = float(row[0]) if row else 0
            conn.commit(); conn.close()
        except Exception as e:
            logger.error("confirmar pedido: %s", e)
            total = 0
        if tipo_entrega == "mostrador":
            dispatcher.utter_message(
                text=f"✅ *Pedido #{pid} confirmado*\n"
                     f"💰 Total: *${total:.2f}*\n"
                     f"Pago: {forma_pago.upper()}\n\n"
                     "Tu pedido estará listo pronto. 🎉")
        else:
            dispatcher.utter_message(
                text=f"✅ *Pedido #{pid} confirmado para envío*\n"
                     f"📍 Dirección: {direccion or '—'}\n"
                     f"💰 Total: *${total:.2f}*\n"
                     f"Pago: {forma_pago.upper()}\n\n"
                     "Asignamos repartidor en breve. 🚚")
        return [AllSlotsReset()]


# ── Acción: Consultar puntos ──────────────────────────────────────────
class ActionConsultarPuntos(Action):
    def name(self) -> Text:
        return "action_consultar_puntos"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero  = tracker.sender_id
        cliente = _buscar_cliente(numero)
        if not cliente:
            dispatcher.utter_message(response="utter_sin_puntos")
            return []
        puntos = cliente.get("puntos", 0)
        nombre = cliente["nombre"].split()[0]
        if puntos == 0:
            dispatcher.utter_message(response="utter_sin_puntos")
        else:
            dispatcher.utter_message(
                text=f"🎯 Hola *{nombre}*\n"
                     f"Tienes *{puntos} puntos* acumulados.\n\n"
                     "Con tus puntos puedes:\n"
                     "• 100 pts → $10 de descuento\n"
                     "• 250 pts → $30 de descuento\n"
                     "• 500 pts → $70 de descuento\n\n"
                     "Escribe *CANJEAR* para usar tus puntos.")
        return [SlotSet("puntos_cliente", float(puntos)),
                SlotSet("nombre_cliente", nombre)]


# ── Acción: Opciones de canje ─────────────────────────────────────────
class ActionOpcionesCanje(Action):
    def name(self) -> Text:
        return "action_opciones_canje"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero  = tracker.sender_id
        cliente = _buscar_cliente(numero)
        puntos  = int(cliente["puntos"]) if cliente else 0
        if puntos < 100:
            dispatcher.utter_message(
                text=f"Necesitas mínimo 100 puntos para canjear.\n"
                     f"Tienes *{puntos} puntos*. ¡Sigue comprando! 🎯")
            return []
        dispatcher.utter_message(
            text=f"🎁 *Canje de puntos — {puntos} pts disponibles*\n\n"
                 + ("1️⃣ 100 pts → $10 de descuento\n" if puntos >= 100 else "")
                 + ("2️⃣ 250 pts → $30 de descuento\n" if puntos >= 250 else "")
                 + ("3️⃣ 500 pts → $70 de descuento\n" if puntos >= 500 else "")
                 + "\nResponde con el número de opción.")
        return []


# ── Acción: Ejecutar canje ────────────────────────────────────────────
class ActionEjecutarCanje(Action):
    def name(self) -> Text:
        return "action_ejecutar_canje"

    OPCIONES = {1: (100, 10.0), 2: (250, 30.0), 3: (500, 70.0)}

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero  = tracker.sender_id
        cliente = _buscar_cliente(numero)
        if not cliente:
            dispatcher.utter_message(text="No encontré tu cuenta. Verifica tu número.")
            return []
        texto = tracker.latest_message.get("text","").strip()
        opcion = None
        for k in ("1","2","3"):
            if k in texto or f"opción {k}" in texto.lower():
                opcion = int(k); break
        if not opcion or opcion not in self.OPCIONES:
            dispatcher.utter_message(text="Elige una opción válida (1, 2 o 3).")
            return []
        pts_req, descuento = self.OPCIONES[opcion]
        if cliente["puntos"] < pts_req:
            dispatcher.utter_message(
                text=f"No tienes suficientes puntos. Necesitas {pts_req}, tienes {cliente['puntos']}.")
            return []
        try:
            conn = _get_conn()
            conn.execute(
                "UPDATE clientes SET puntos=puntos-? WHERE id=?",
                (pts_req, cliente["id"]))
            conn.execute("""
                INSERT INTO historico_puntos
                (cliente_id, tipo, puntos, descripcion, fecha)
                VALUES(?,'-',?,?,datetime('now'))""",
                (cliente["id"], pts_req, f"Canje WA: ${descuento:.0f} descuento"))
            conn.commit(); conn.close()
            dispatcher.utter_message(
                text=f"✅ *¡Canje realizado!*\n"
                     f"Canjeaste *{pts_req} puntos* = *${descuento:.2f} de descuento*.\n"
                     "Aplica en tu próxima compra. 🎉")
        except Exception as e:
            logger.error("canje: %s", e)
            dispatcher.utter_message(text="Error al procesar el canje. Intenta de nuevo.")
        return []


# ── Acción: Estado del pedido ─────────────────────────────────────────
class ActionEstadoPedido(Action):
    def name(self) -> Text:
        return "action_estado_pedido"

    EMOJIS = {
        "nuevo": "🆕", "confirmado": "✅", "pesando": "⚖️",
        "listo": "📦", "entregado": "✅", "cancelado": "❌"
    }

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero = tracker.sender_id
        try:
            conn = _get_conn()
            rows = conn.execute("""
                SELECT id, estado, total, tipo_entrega, fecha
                FROM pedidos_whatsapp
                WHERE numero_whatsapp=? AND estado NOT IN ('cancelado')
                ORDER BY id DESC LIMIT 3""",
                (numero,)).fetchall()
            conn.close()
            if not rows:
                dispatcher.utter_message(
                    text="No encontré pedidos activos para tu número.")
                return []
            msg = "📋 *Tus pedidos recientes:*\n\n"
            for r in rows:
                emoji = self.EMOJIS.get(r[1], "•")
                msg += (f"{emoji} Pedido *#{r[0]}*\n"
                        f"   Estado: *{r[1].upper()}*\n"
                        f"   Total: ${float(r[2]):.2f}\n"
                        f"   Entrega: {r[3]}\n\n")
            dispatcher.utter_message(text=msg.strip())
        except Exception as e:
            logger.error("estado_pedido: %s", e)
            dispatcher.utter_message(text="No pude consultar tu pedido. Intenta de nuevo.")
        return []


# ── Acción: Generar link de pago ──────────────────────────────────────
class ActionGenerarLinkPago(Action):
    def name(self) -> Text:
        return "action_generar_link_pago"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        pid = tracker.get_slot("pedido_id")
        if not pid:
            dispatcher.utter_message(text="No hay pedido activo para generar link.")
            return []
        try:
            # Agregar sys.path para importar servicios SPJ
            root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            if root not in sys.path: sys.path.insert(0, root)
            from services.mercado_pago_service import MercadoPagoService
            conn  = _get_conn()
            row   = conn.execute(
                "SELECT total FROM pedidos_whatsapp WHERE id=?", (pid,)).fetchone()
            total = float(row[0]) if row else 0
            svc   = MercadoPagoService(conn)
            url   = svc.crear_link(total=total, pedido_id=int(pid))
            conn.close()
            if url:
                dispatcher.utter_message(
                    text=f"🔗 *Link de pago*\nMonto: *${total:.2f}*\n{url}\n\n"
                         "Te confirmamos cuando se procese el pago.")
            else:
                dispatcher.utter_message(
                    text="No pude generar el link. ¿Prefieres pagar en efectivo?")
        except Exception as e:
            logger.error("generar_link: %s", e)
            dispatcher.utter_message(
                text="Error al generar link de pago. ¿Prefieres efectivo?")
        return []


# ── Validador del form de dirección ──────────────────────────────────
class ValidateFormDireccion(FormValidationAction):
    def name(self) -> Text:
        return "validate_form_direccion"

    def validate_direccion_entrega(
        self, slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        if slot_value and len(str(slot_value).strip()) >= 10:
            return {"direccion_entrega": str(slot_value).strip()}
        dispatcher.utter_message(
            text="Por favor escribe tu dirección completa (calle, número, colonia).")
        return {"direccion_entrega": None}


# ─────────────────────────────────────────────────────────────────────────────
# ActionProcesarVentaWhatsApp — fusionado desde rasa_project/actions/actions.py
# Usa app_container para acceso a SalesService y WhatsAppService del ERP.
# ─────────────────────────────────────────────────────────────────────────────
if _RASA_OK:
    class ActionProcesarVentaWhatsApp(Action):
        """
        Crea una venta completa desde un pedido de WhatsApp usando el ERP.
        Requiere slots: producto (str), cantidad (float).
        Registra la venta en BD y envía link de pago al cliente.
        """
        def name(self) -> Text:
            return "action_procesar_venta_whatsapp"

        def run(self, dispatcher: CollectingDispatcher,
                tracker: Tracker,
                domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
            telefono_cliente     = tracker.sender_id
            producto_solicitado  = tracker.get_slot("producto") or ""
            try:
                cantidad_solicitada = float(tracker.get_slot("cantidad") or 1.0)
            except (ValueError, TypeError):
                cantidad_solicitada = 1.0

            try:
                # Importar app_container solo cuando Rasa este en ejecucion
                import sys, os
                # Agregar raiz del proyecto al path si no esta
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))))
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)

                from core.app_container import container

                # Buscar producto en ERP
                conn = _get_conn()
                row = conn.execute(
                    "SELECT id, precio_venta FROM productos "
                    "WHERE LOWER(nombre) LIKE ? AND activo=1 LIMIT 1",
                    (f"%{producto_solicitado.lower()}%",)
                ).fetchone()
                if not row:
                    dispatcher.utter_message(
                        text=f"No encontre '{producto_solicitado}' en nuestro catalogo.")
                    return []

                producto_id, precio_unitario = row[0], float(row[1])
                carrito = [{
                    "product_id": producto_id,
                    "qty": cantidad_solicitada,
                    "unit_price": precio_unitario,
                    "es_compuesto": 0,
                }]

                # Registrar venta en ERP
                folio = container.sales_service.execute_sale(
                    branch_id=1,
                    user="Bot_Rasa",
                    items=carrito,
                    payment_method="Link de Pago",
                    amount_paid=0.0,
                    client_id=None,
                    notes=f"Venta WhatsApp automatizada a {telefono_cliente}",
                )

                # Enviar link de pago
                total = cantidad_solicitada * precio_unitario
                container.whatsapp_service.send_payment_link(
                    branch_id=1,
                    phone=telefono_cliente,
                    order_id=folio,
                    amount=total,
                )
                container.whatsapp_service.send_psychological_message(
                    1, telefono_cliente, "gamification")

                dispatcher.utter_message(
                    text=f"Listo! Orden #{folio} registrada. Te envie el link de pago.")

            except ValueError as ve:
                dispatcher.utter_message(text=f"No pudimos procesar tu pedido: {ve}")
            except Exception as e:
                logger.error("ActionProcesarVentaWhatsApp: %s", e)
                dispatcher.utter_message(
                    text="Hubo un error interno. Un asesor te atendera pronto.")

            return []
