# services/bot_pedidos.py — SPJ POS v13
"""
Bot conversacional para pedidos y cotizaciones por WhatsApp.

Flujo de PEDIDO:
  inicio → [seleccionar_sucursal] → [hora_deseada] →
  recibir_pedido → confirmar_pedido → tipo_entrega → forma_pago →
  [espera_direccion] → completado

Flujo de COTIZACIÓN:
  inicio → [seleccionar_sucursal] → solicitar_cotizacion →
  confirmar_cotizacion → [anticipo] → orden_creada → completado

Novedades v13:
  - Verifica horario de sucursal (rechaza/programa si está cerrada)
  - Pregunta sucursal si el número es compartido
  - Pregunta hora deseada para prioridad
  - Flujo completo de cotización con anticipos
  - Recordatorios automáticos por scheduler
"""
from __future__ import annotations
import json, logging, re, uuid
from datetime import datetime, date, timedelta
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.bot")

_RE_ITEM = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|gramos?|g|piezas?|pzs?|pz)?(?:\s+de)?\s+([a-záéíóúñü\s]+)",
    re.IGNORECASE | re.UNICODE
)
_RE_HORA = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)

PALABRAS_CONFIRMAR = {"si","sí","yes","ok","va","dale","confirmo","bueno","claro","correcto"}
PALABRAS_CANCELAR  = {"no","nop","nope","cancelar","cancel","chale"}
PALABRAS_MENU      = {"menu","menú","productos","precios","carta","lista"}
PALABRAS_PUNTOS    = {"puntos","recompensa","saldo","fidelidad"}
PALABRAS_COTIZAR   = {"cotizacion","cotización","cotizar","presupuesto","precio","cuanto","cuánto",
                      "pedido grande","para el","para mañana","para el viernes"}

OPCIONES_HORA = {
    "1": ("lo_antes_posible", "Lo antes posible", "alta"),
    "2": ("en_30min",         "En 30 minutos",    "alta"),
    "3": ("en_1hora",         "En 1 hora",        "normal"),
    "4": ("en_la_tarde",      "Hoy en la tarde",  "baja"),
}


class BotPedidos:
    """Máquina de estados conversacional para un número de WhatsApp."""

    def __init__(self, numero: str, conn=None, sucursal_id: int = None):
        self.numero     = numero
        self.conn       = conn or get_connection()
        self._sucursal_id_forzado = sucursal_id  # cuando el número es exclusivo de 1 sucursal
        self._state     = self._load_state()
        # v13.1: UC disponible si se pasa container
        self._container = None   # set via set_container()

    def set_container(self, container) -> None:
        """Inyecta el AppContainer para usar los casos de uso v13.1."""
        self._container = container
        if container and hasattr(container, 'db'):
            self.conn = container.db

    # ── Estado persistente ─────────────────────────────────────────────────
    def _load_state(self) -> dict:
        row = self.conn.execute(
            "SELECT datos FROM bot_sessions WHERE numero=?",
            (self.numero,)
        ).fetchone()
        if row:
            try: return json.loads(row[0])
            except Exception: pass
        return {"paso": "inicio", "items": [], "pedido_id": None,
                "tipo_entrega": None, "forma_pago": None,
                "sucursal_id": self._sucursal_id_forzado,
                "hora_deseada": None, "prioridad": "normal",
                "es_cotizacion": False, "cotizacion_id": None,
                "orden_numero": None}

    def _save_state(self):
        self.conn.execute("""
            INSERT OR REPLACE INTO bot_sessions
                (numero, datos, ultima_actividad)
            VALUES (?,?,datetime('now'))
        """, (self.numero, json.dumps(self._state, default=str)))
        try: self.conn.commit()
        except Exception: pass

    def reset(self):
        self._state = {"paso": "inicio", "items": [], "pedido_id": None,
                       "tipo_entrega": None, "forma_pago": None,
                       "sucursal_id": self._sucursal_id_forzado,
                       "hora_deseada": None, "prioridad": "normal",
                       "es_cotizacion": False, "cotizacion_id": None,
                       "orden_numero": None}
        self._save_state()

    # ── Dispatcher ─────────────────────────────────────────────────────────
    def procesar(self, texto: str) -> list:
        texto = texto.strip()
        paso  = self._state.get("paso", "inicio")

        # Comandos globales
        if any(p in texto.lower().split() for p in PALABRAS_CANCELAR):
            self.reset()
            return ["❌ Pedido cancelado. Cuando quieras, escríbeme de nuevo. 👋"]
        if any(p in texto.lower().split() for p in PALABRAS_MENU):
            return [self._get_menu()]
        if any(p in texto.lower().split() for p in PALABRAS_PUNTOS):
            return [self._get_puntos()]

        # Intentar Rasa si está configurado
        rasa_resp = self._try_rasa(texto)
        if rasa_resp:
            return rasa_resp

        # ── Paso: inicio ──────────────────────────────────────────────────
        if paso in ("inicio", "espera_pedido"):
            # Detectar intención de cotización
            texto_lower = texto.lower()
            es_cotizacion = any(p in texto_lower for p in PALABRAS_COTIZAR)
            if es_cotizacion:
                self._state["es_cotizacion"] = True
            return self._paso_inicio(texto)

        # ── Paso: seleccionar_sucursal ────────────────────────────────────
        if paso == "seleccionar_sucursal":
            return self._paso_seleccionar_sucursal(texto)

        # ── Paso: hora_deseada ────────────────────────────────────────────
        if paso == "hora_deseada":
            return self._paso_hora_deseada(texto)

        # ── Pasos de pedido normal ────────────────────────────────────────
        if paso == "recibir_pedido":
            return self._paso_recibir_pedido(texto)
        if paso == "confirmar_pedido":
            return self._paso_confirmar(texto)
        if paso == "tipo_entrega":
            return self._paso_tipo_entrega(texto)
        if paso == "forma_pago":
            return self._paso_forma_pago(texto)
        if paso == "espera_direccion":
            return self._paso_recibir_direccion(texto)

        # ── Pasos de cotización ───────────────────────────────────────────
        if paso == "solicitar_cotizacion":
            return self._paso_solicitar_cotizacion(texto)
        if paso == "confirmar_cotizacion":
            return self._paso_confirmar_cotizacion(texto)
        if paso == "fecha_entrega_cotizacion":
            return self._paso_fecha_entrega(texto)
        if paso == "anticipo_cotizacion":
            return self._paso_anticipo(texto)

        return self._paso_inicio(texto)

    # ── Paso: inicio / detección ───────────────────────────────────────────
    def _paso_inicio(self, texto: str) -> list:
        # 1. Verificar si necesita elegir sucursal
        sucursales = self._get_sucursales_disponibles()
        if len(sucursales) > 1 and not self._state.get("sucursal_id"):
            self._state["paso"] = "seleccionar_sucursal"
            self._save_state()
            return [self._msg_seleccionar_sucursal(sucursales)]

        # Si solo hay una o está forzada, asignarla
        if not self._state.get("sucursal_id"):
            if sucursales:
                self._state["sucursal_id"] = sucursales[0]["id"]
            else:
                self._state["sucursal_id"] = 1

        # 2. Verificar horario
        suc_id = self._state["sucursal_id"]
        abierto, msg_cerrado = self._verificar_horario(suc_id)
        if not abierto:
            # ¿Acepta pedidos programados?
            acepta = self._get_sucursal_config(suc_id, "acepta_pedidos_fuera_horario", "1")
            if acepta == "0":
                self.reset()
                return [msg_cerrado]
            else:
                self._state["programado"] = True
                resp = [msg_cerrado,
                        "Tu pedido quedará *programado* y lo atenderemos al abrir. ¿Deseas continuar? (sí/no)"]
                self._state["paso"] = "confirmar_programado"
                self._save_state()
                return resp

        # 3. Redirigir al flujo correcto
        if self._state.get("es_cotizacion"):
            self._state["paso"] = "solicitar_cotizacion"
            self._save_state()
            return [("📋 *Cotización SPJ*\n\n"
                     "Dime qué productos necesitas y para qué fecha.\n"
                     "Ejemplo: _5kg pechuga, 3kg pierna, para el viernes_")]
        else:
            return self._paso_recibir_pedido(texto)

    # ── Sucursales ─────────────────────────────────────────────────────────
    def _get_sucursales_disponibles(self) -> list:
        if self._sucursal_id_forzado:
            try:
                row = self.conn.execute(
                    "SELECT id, nombre, direccion FROM sucursales WHERE id=? AND activa=1",
                    (self._sucursal_id_forzado,)
                ).fetchone()
                return [dict(row)] if row else []
            except Exception:
                return []
        try:
            rows = self.conn.execute(
                "SELECT id, nombre, direccion FROM sucursales WHERE activa=1 ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _msg_seleccionar_sucursal(self, sucursales: list) -> str:
        lines = ["📍 *¿En cuál sucursal deseas tu pedido?*\n"]
        for i, s in enumerate(sucursales, 1):
            addr = s.get("direccion", "")
            lines.append(f"{i}️⃣ {s['nombre']}" + (f" — {addr}" if addr else ""))
        lines.append("\nResponde con el número de tu sucursal.")
        return "\n".join(lines)

    def _paso_seleccionar_sucursal(self, texto: str) -> list:
        sucursales = self._get_sucursales_disponibles()
        idx = None
        if texto.strip().isdigit():
            idx = int(texto.strip()) - 1
        if idx is not None and 0 <= idx < len(sucursales):
            suc = sucursales[idx]
            self._state["sucursal_id"] = suc["id"]
            # Verificar horario de la sucursal elegida
            abierto, msg = self._verificar_horario(suc["id"])
            if not abierto:
                # Buscar otras abiertas
                otras_abiertas = [s for s in sucursales
                                  if s["id"] != suc["id"] and self._verificar_horario(s["id"])[0]]
                if otras_abiertas:
                    alt = otras_abiertas[0]
                    self._state["paso"] = "seleccionar_sucursal"
                    self._save_state()
                    return [f"La sucursal *{suc['nombre']}* está cerrada en este momento.\n\n"
                            f"Sin embargo, *{alt['nombre']}* sigue abierta.\n"
                            f"¿Prefieres ir ahí? (sí / no)"]
                acepta = self._get_sucursal_config(suc["id"], "acepta_pedidos_fuera_horario", "1")
                if acepta == "0":
                    self.reset()
                    return [msg]
                self._state["programado"] = True

            if self._state.get("es_cotizacion"):
                self._state["paso"] = "solicitar_cotizacion"
                self._save_state()
                return ["✅ Sucursal seleccionada: *" + suc['nombre'] + "*\n\n"
                        "📋 Dime qué productos necesitas y para qué fecha.\n"
                        "Ejemplo: _5kg pechuga, 3kg pierna, para el viernes_"]
            else:
                self._state["paso"] = "hora_deseada"
                self._save_state()
                return ["✅ Sucursal: *" + suc['nombre'] + "*\n\n" + self._msg_hora_deseada()]
        return ["Por favor responde con el número de la sucursal (1, 2, 3...).\n\n"
                + self._msg_seleccionar_sucursal(sucursales)]

    # ── Horario ────────────────────────────────────────────────────────────
    def _verificar_horario(self, sucursal_id: int) -> tuple:
        """Retorna (abierto: bool, mensaje_cerrado: str)."""
        try:
            row = self.conn.execute("""
                SELECT hora_apertura, hora_cierre, dias_operacion,
                       mensaje_fuera_horario, acepta_pedidos_fuera_horario
                FROM sucursales WHERE id=?
            """, (sucursal_id,)).fetchone()
            if not row or not row[0]:
                return True, ""  # Sin configuración = siempre abierto

            ahora     = datetime.now()
            dia_hoy   = str(ahora.isoweekday())  # 1=lun … 7=dom
            hora_act  = ahora.strftime("%H:%M")
            dias_op   = (row[2] or "1,2,3,4,5,6").split(",")
            hora_abre = row[0] or "08:00"
            hora_cie  = row[1] or "21:00"
            msg       = row[3] or "Estamos cerrados. Te atendemos en horario de operación."

            if dia_hoy not in dias_op:
                return False, msg
            if hora_abre <= hora_act <= hora_cie:
                return True, ""
            return False, msg
        except Exception:
            return True, ""

    def _get_sucursal_config(self, sucursal_id: int, campo: str, default: str) -> str:
        try:
            row = self.conn.execute(
                f"SELECT {campo} FROM sucursales WHERE id=?", (sucursal_id,)
            ).fetchone()
            return str(row[0]) if row and row[0] is not None else default
        except Exception:
            return default

    # ── Hora deseada ───────────────────────────────────────────────────────
    def _msg_hora_deseada(self) -> str:
        return ("⏰ *¿Para qué hora necesitas tu pedido?*\n\n"
                "1️⃣ Lo antes posible (prioridad alta)\n"
                "2️⃣ En 30 minutos\n"
                "3️⃣ En 1 hora\n"
                "4️⃣ Hoy en la tarde (después de las 3pm)\n"
                "5️⃣ Otra hora (escríbela, ej: _2:30 pm_)\n\n"
                "Esto nos ayuda a preparar tu pedido a tiempo 🙌")

    def _paso_hora_deseada(self, texto: str) -> list:
        t = texto.strip()
        if t in OPCIONES_HORA:
            val, label, prioridad = OPCIONES_HORA[t]
            self._state["hora_deseada"] = label
            self._state["prioridad"]    = prioridad
        elif t == "5" or _RE_HORA.search(t):
            m = _RE_HORA.search(t)
            if m:
                h = int(m.group(1)); mn = int(m.group(2) or 0)
                ap = (m.group(3) or "").lower()
                if ap == "pm" and h < 12: h += 12
                hora_str = f"{h:02d}:{mn:02d}"
                self._state["hora_deseada"] = hora_str
                prioridad = "alta" if h < datetime.now().hour + 1 else "normal"
                self._state["prioridad"] = prioridad
            else:
                self._state["hora_deseada"] = texto.strip()
                self._state["prioridad"]    = "normal"
        else:
            return ["Por favor elige una opción (1-5) o escribe la hora.\n\n"
                    + self._msg_hora_deseada()]

        self._state["paso"] = "recibir_pedido"
        self._save_state()
        hora_label = self._state["hora_deseada"]
        return [f"⏰ Anotado: *{hora_label}*\n\n"
                "Ahora dime qué necesitas. Ejemplo:\n"
                "_1kg pechuga, 2kg pierna_\n"
                "o escribe *MENU* para ver productos."]

    # ── Pedido normal ──────────────────────────────────────────────────────
    def _paso_recibir_pedido(self, texto: str) -> list:
        items = self._parsear_items(texto)
        if not items:
            return [("No entendí tu pedido. 😅\n"
                     "Escríbelo así: _1kg pechuga, 2kg pierna_\n"
                     "o escribe *MENU* para ver productos.\n"
                     "Para cotización escribe *COTIZAR*.")]
        self._state["items"] = items
        self._state["paso"]  = "confirmar_pedido"
        self._save_state()
        total_est = sum(i["subtotal"] for i in items)
        detalle   = self._formato_items(items)
        hora = self._state.get("hora_deseada", "")
        hora_txt  = f"\n⏰ Para: *{hora}*" if hora else ""
        return [f"🛒 *Resumen de tu pedido:*\n\n{detalle}\n"
                f"💰 Estimado: ${total_est:.2f}{hora_txt}\n\n"
                f"¿Confirmas? (sí/no)"]

    def _paso_confirmar(self, texto: str) -> list:
        if any(p in texto.lower().split() for p in PALABRAS_CONFIRMAR):
            pedido_id = self._crear_pedido()
            if not pedido_id:
                self.reset()
                return ["Hubo un error al crear tu pedido. Intenta de nuevo."]
            self._state["pedido_id"] = pedido_id
            self._state["paso"]      = "tipo_entrega"
            self._save_state()
            return [("✅ Pedido creado.\n\n"
                     "¿Cómo lo quieres recibir?\n"
                     "1️⃣ Recoger en mostrador\n"
                     "2️⃣ Envío a domicilio")]
        else:
            self._state["paso"] = "recibir_pedido"
            self._save_state()
            return ["Ok, ¿qué deseas cambiar? Escribe el pedido de nuevo."]

    def _paso_tipo_entrega(self, texto: str) -> list:
        t = texto.strip().lower()
        if t == "1" or "mostrador" in t or "recoger" in t:
            self._state["tipo_entrega"] = "mostrador"
        elif t == "2" or "domicilio" in t or "envío" in t or "envio" in t:
            self._state["tipo_entrega"] = "delivery"
        else:
            return ["Por favor elige:\n1️⃣ Recoger en mostrador\n2️⃣ Envío a domicilio"]
        self._state["paso"] = "forma_pago"
        self._save_state()
        total = self._get_total_pedido()
        return [self._msg_forma_pago(total)]

    def _paso_forma_pago(self, texto: str) -> list:
        t = texto.strip(); total = self._get_total_pedido()
        if t == "1" or "efectivo" in t.lower():
            self._state["forma_pago"] = "efectivo"
        elif t == "2" or "tarjeta" in t.lower():
            self._state["forma_pago"] = "tarjeta"
        elif t == "3" or "link" in t.lower() or "mercado" in t.lower():
            return self._generar_link_pago(total)
        else:
            return [self._msg_forma_pago(total)]

        if self._state["tipo_entrega"] == "delivery":
            self._state["paso"] = "espera_direccion"
            self._save_state()
            return ["📍 ¿Cuál es tu dirección de entrega?"]

        self._finalizar_pedido()
        prioridad = self._state.get("prioridad", "normal")
        emoji = "🔴" if prioridad == "alta" else "🟡"
        return [f"✅ {emoji} *Pedido confirmado!*\n"
                f"Paga *en {self._state['forma_pago']}* al recoger.\n"
                f"Estaremos preparando tu pedido. 🔪"]

    def _paso_recibir_direccion(self, texto: str) -> list:
        self._state["direccion"] = texto.strip()
        self._state["paso"]      = "completado"
        self._save_state()
        self.conn.execute("""
            UPDATE pedidos_whatsapp
            SET tipo_entrega=?, forma_pago=?, direccion_entrega=?,
                estado='confirmado', fecha_confirmacion=datetime('now')
            WHERE id=?
        """, (self._state.get("tipo_entrega"),
              self._state.get("forma_pago"),
              texto.strip(),
              self._state.get("pedido_id")))
        try: self.conn.commit()
        except Exception: pass
        return [f"📍 Dirección: *{texto.strip()}*\n\n"
                "🚚 Asignaremos un repartidor en breve. "
                "Te avisamos cuando salga tu pedido."]

    # ── Flujo cotización ───────────────────────────────────────────────────
    def _paso_solicitar_cotizacion(self, texto: str) -> list:
        """Recopila productos y fecha de entrega de la cotización."""
        items = self._parsear_items(texto)
        # Buscar fecha en el texto
        fecha_str = self._extraer_fecha(texto)

        if not items:
            return ["Dime qué productos necesitas.\n"
                    "Ejemplo: _5kg pechuga fileteada, 3kg costilla_"]

        self._state["items"]        = items
        self._state["fecha_entrega"] = fecha_str
        self._state["paso"]         = "confirmar_cotizacion" if fecha_str else "fecha_entrega_cotizacion"
        self._save_state()

        if not fecha_str:
            return [self._resumen_cotizacion(items) +
                    "\n\n📅 ¿Para qué fecha necesitas la entrega?\n"
                    "Ejemplo: _viernes_, _20 de marzo_, _mañana_"]

        return [self._resumen_cotizacion(items) +
                f"\n\n📅 Fecha de entrega: *{fecha_str}*\n\n"
                f"¿Confirmas esta cotización? (sí/no/modificar)"]

    def _paso_fecha_entrega(self, texto: str) -> list:
        fecha = self._extraer_fecha(texto) or texto.strip()
        self._state["fecha_entrega"] = fecha
        self._state["paso"] = "confirmar_cotizacion"
        self._save_state()
        items = self._state.get("items", [])
        return [self._resumen_cotizacion(items) +
                f"\n\n📅 Fecha de entrega: *{fecha}*\n\n"
                f"¿Confirmas? (sí/no/modificar)"]

    def _paso_confirmar_cotizacion(self, texto: str) -> list:
        t = texto.lower().strip()
        if any(p in t.split() for p in PALABRAS_CANCELAR):
            self.reset()
            return ["❌ Cotización cancelada."]
        if "modif" in t or "cambiar" in t:
            self._state["paso"] = "solicitar_cotizacion"
            self._save_state()
            return ["Ok, ¿qué deseas cambiar? Escribe los productos de nuevo."]
        if any(p in t.split() for p in PALABRAS_CONFIRMAR):
            return self._crear_cotizacion_y_calcular_anticipo()
        return [self._resumen_cotizacion(self._state.get("items", [])) +
                "\n\n¿Confirmas esta cotización? (sí/no/modificar)"]

    def _crear_cotizacion_y_calcular_anticipo(self) -> list:
        """Crea la cotización en BD y calcula el anticipo."""
        items     = self._state.get("items", [])
        fecha_ent = self._state.get("fecha_entrega", "")
        suc_id    = self._state.get("sucursal_id", 1)
        cliente   = self._get_cliente()
        total     = sum(i["subtotal"] for i in items)

        try:
            # Crear cotización
            folio = f"COT-{uuid.uuid4().hex[:6].upper()}"
            cliente_id = cliente["id"] if cliente else None
            with transaction(self.conn) as c:
                cot_id = c.execute("""
                    INSERT INTO cotizaciones
                        (folio, cliente_id, cliente_nombre, subtotal, total,
                         estado, vigencia_dias, fecha_vencimiento, sucursal_id)
                    VALUES (?,?,?,?,?,'pendiente',2,date('now','+2 days'),?)
                """, (folio, cliente_id,
                      cliente["nombre"] if cliente else self.numero,
                      total, total, suc_id)
                ).lastrowid
                for item in items:
                    c.execute("""
                        INSERT INTO cotizaciones_detalle
                            (cotizacion_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
                        VALUES (?,?,?,?,?,?)
                    """, (cot_id, item.get("producto_id"), item["nombre_producto"],
                          item["cantidad_pedida"], item["precio_unitario"], item["subtotal"]))

            self._state["cotizacion_id"] = cot_id

            # Calcular anticipo
            try:
                from core.services.anticipo_service import AnticipoCotizacionService
                ant_svc = AnticipoCotizacionService(self.conn)
                # Build items with categoria
                items_con_cat = []
                for item in items:
                    cat = ""
                    try:
                        row = self.conn.execute(
                            "SELECT categoria FROM productos WHERE id=?",
                            (item.get("producto_id", 0),)
                        ).fetchone()
                        cat = row[0] if row else ""
                    except Exception:
                        pass
                    items_con_cat.append({"categoria": cat, "subtotal": item["subtotal"]})

                nivel = (cliente.get("nivel_fidelidad", "Bronce")
                         if cliente else "Bronce")
                anticipo = ant_svc.calcular(total, items_con_cat, cliente_id, nivel)
            except Exception as e:
                logger.debug("anticipo calc: %s", e)
                anticipo = {"requiere": False, "pct": 0, "monto": 0, "razon": "", "exento": True}

            self._state["anticipo_info"] = anticipo

            # Construir respuesta
            resumen = self._resumen_cotizacion(items)
            msg = (f"✅ *Cotización {folio} generada!*\n\n"
                   f"{resumen}\n\n"
                   f"📅 Fecha de entrega: *{fecha_ent}*\n"
                   f"⏱ Válida por 48 horas\n")

            if anticipo["requiere"]:
                self._state["paso"] = "anticipo_cotizacion"
                self._save_state()
                msg += (f"\n💰 *Anticipo requerido: ${anticipo['monto']:.2f}* "
                        f"({anticipo['pct']:.0f}%)\n"
                        f"_{anticipo['razon']}_\n\n"
                        f"¿Cómo prefieres pagar el anticipo?\n"
                        f"1️⃣ Link de pago (MercadoPago)\n"
                        f"2️⃣ Efectivo en sucursal\n"
                        f"3️⃣ Ya pagué / tengo referencia")
                return [msg]
            else:
                # Sin anticipo — crear orden directo
                return self._crear_orden_directo(cot_id, fecha_ent, anticipo, folio)

        except Exception as e:
            logger.error("_crear_cotizacion: %s", e)
            self.reset()
            return ["Hubo un error al generar tu cotización. Intenta de nuevo."]

    def _paso_anticipo(self, texto: str) -> list:
        t = texto.strip()
        cot_id    = self._state.get("cotizacion_id")
        anticipo  = self._state.get("anticipo_info", {})
        fecha_ent = self._state.get("fecha_entrega", "")

        if t == "1" or "link" in t.lower() or "mercado" in t.lower():
            try:
                from services.mercado_pago_service import MercadoPagoService
                mp = MercadoPagoService(self.conn)
                result = mp.crear_link(
                    total=anticipo.get("monto", 0),
                    pedido_id=cot_id,
                    descripcion=f"Anticipo cotización COT-{cot_id}"
                )
                link = result.get("link", result.get("url", ""))
                if link:
                    self._state["paso"] = "esperando_pago_anticipo"
                    self._save_state()
                    return [f"🔗 Tu link de pago:\n{link}\n\n"
                            f"Monto: *${anticipo['monto']:.2f}*\n"
                            "Avísame cuando hayas pagado."]
            except Exception as e:
                logger.debug("MP anticipo: %s", e)
            return ["No pude generar el link. Puedes pagar en efectivo en sucursal.\n"
                    "¿Confirmas pago en efectivo? (sí)"]

        elif t == "2" or "efectivo" in t.lower():
            self._state["paso"] = "completado"
            self._save_state()
            return self._crear_orden_directo(
                cot_id, fecha_ent, anticipo, f"COT-{cot_id}",
                metodo_anticipo="efectivo_pendiente"
            )

        elif t == "3" or "pagué" in t.lower() or "referencia" in t.lower():
            self._state["paso"] = "completado"
            self._save_state()
            return self._crear_orden_directo(
                cot_id, fecha_ent, anticipo, f"COT-{cot_id}",
                metodo_anticipo="manual_confirmado"
            )

        return [f"¿Cómo prefieres pagar el anticipo de ${anticipo.get('monto',0):.2f}?\n"
                "1️⃣ Link MercadoPago\n"
                "2️⃣ Efectivo en sucursal\n"
                "3️⃣ Ya pagué"]

    def _crear_orden_directo(self, cot_id: int, fecha_ent: str,
                              anticipo: dict, folio: str,
                              metodo_anticipo: str = "") -> list:
        """Crea la ordenes_cotizacion y notifica."""
        cliente = self._get_cliente()
        suc_id  = self._state.get("sucursal_id", 1)
        try:
            from core.services.anticipo_service import AnticipoCotizacionService
            ant_svc = AnticipoCotizacionService(self.conn)
            result  = ant_svc.crear_orden(
                cotizacion_id=cot_id,
                cliente_id=cliente["id"] if cliente else None,
                sucursal_id=suc_id,
                fecha_entrega=fecha_ent,
                hora_entrega=self._state.get("hora_deseada", ""),
                tipo_entrega=self._state.get("tipo_entrega", "mostrador"),
                usuario="bot_whatsapp",
                anticipo_info=anticipo,
                notas=f"Pedido via WhatsApp {self.numero}"
            )
            num_orden = result["numero_orden"]
            self._state["orden_numero"] = num_orden
            self._state["paso"]         = "completado"
            self._save_state()

            if metodo_anticipo:
                self.conn.execute(
                    "UPDATE ordenes_cotizacion SET metodo_anticipo=? WHERE numero_orden=?",
                    (metodo_anticipo, num_orden))
                try: self.conn.commit()
                except Exception: pass

            # Publicar evento para notificación en POS
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PEDIDO_NUEVO", {
                    "tipo": "cotizacion", "orden": num_orden,
                    "sucursal_id": suc_id,
                    "cliente": cliente["nombre"] if cliente else self.numero
                })
            except Exception:
                pass

            saldo = anticipo.get("monto", 0)
            total = self.conn.execute(
                "SELECT total FROM cotizaciones WHERE id=?", (cot_id,)
            ).fetchone()
            total_val = float(total[0]) if total else 0
            pendiente = total_val - saldo

            msg_cliente = (f"✅ *Orden {num_orden} confirmada!*\n\n"
                          f"📅 Entrega: *{fecha_ent}*\n")
            if saldo > 0:
                msg_cliente += (f"💳 Anticipo: ${saldo:.2f}\n"
                               f"💰 Pagas al recoger: ${pendiente:.2f}\n")
            else:
                msg_cliente += f"💰 Total a pagar: ${total_val:.2f}\n"
            msg_cliente += "\nTe avisamos cuando esté listo. ¡Gracias! 🙌"

            return [msg_cliente]
        except Exception as e:
            logger.error("_crear_orden_directo: %s", e)
            return [f"Orden registrada (folio: {folio}). "
                    "Te confirmamos a la brevedad. ¡Gracias!"]

    # ── Helpers ────────────────────────────────────────────────────────────
    def _parsear_items(self, texto: str) -> list:
        items = []
        for m in _RE_ITEM.finditer(texto):
            cant = float(m.group(1).replace(",", "."))
            nombre = m.group(2).strip().rstrip()
            if len(nombre) < 2:
                continue
            try:
                row = self.conn.execute(
                    "SELECT id, nombre, precio, categoria "
                    "FROM productos WHERE activo=1 "
                    "AND (lower(nombre) LIKE ? OR lower(nombre) LIKE ?) LIMIT 1",
                    (f"%{nombre.lower()}%", f"{nombre.lower()}%")
                ).fetchone()
                if row:
                    items.append({
                        "producto_id":     row[0],
                        "nombre_producto": row[1],
                        "cantidad_pedida": cant,
                        "precio_unitario": float(row[2]),
                        "subtotal":        round(cant * float(row[2]), 2),
                        "unidad":          "kg",
                    })
            except Exception:
                pass
        return items

    def _formato_items(self, items: list) -> str:
        lines = []
        for i in items:
            lines.append(
                f"• {i['nombre_producto']} {i['cantidad_pedida']:.1f}kg "
                f"× ${i['precio_unitario']:.2f} = *${i['subtotal']:.2f}*"
            )
        total = sum(i["subtotal"] for i in items)
        lines.append(f"\n*Total: ${total:.2f}*")
        return "\n".join(lines)

    def _resumen_cotizacion(self, items: list) -> str:
        return "📋 *Resumen de cotización:*\n\n" + self._formato_items(items)

    def _extraer_fecha(self, texto: str) -> str:
        """Extrae una fecha del texto del cliente."""
        hoy = date.today()
        t = texto.lower()
        if "hoy" in t:
            return hoy.strftime("%d/%m/%Y")
        if "mañana" in t:
            return (hoy + timedelta(days=1)).strftime("%d/%m/%Y")
        dias = {"lunes":0,"martes":1,"miércoles":2,"miercoles":2,
                "jueves":3,"viernes":4,"sábado":5,"sabado":5,"domingo":6}
        for nombre, num in dias.items():
            if nombre in t:
                diff = (num - hoy.weekday()) % 7 or 7
                return (hoy + timedelta(days=diff)).strftime("%d/%m/%Y")
        m = re.search(r"(\d{1,2})\s+de\s+(\w+)", t)
        if m:
            return f"{m.group(1)} de {m.group(2)}"
        return ""

    def _msg_forma_pago(self, total: float) -> str:
        return (f"💰 Total: *${total:.2f}*\n\n"
                "¿Cómo deseas pagar?\n"
                "1️⃣ Efectivo\n"
                "2️⃣ Tarjeta\n"
                "3️⃣ Link de pago (MercadoPago)")

    def _generar_link_pago(self, total: float) -> list:
        pid = self._state.get("pedido_id")
        try:
            from services.mercado_pago_service import MercadoPagoService
            mp = MercadoPagoService(self.conn)
            result = mp.crear_link(total=total, pedido_id=pid,
                                   descripcion="Pedido SPJ")
            link = result.get("link", result.get("url", ""))
            if link:
                self._state["paso"] = "completado"
                self._save_state()
                return [f"🔗 Tu link de pago:\n{link}\n\nMonto: *${total:.2f}*"]
        except Exception as e:
            logger.debug("MP link: %s", e)
        return ["No pude generar el link. Elige otra forma de pago:\n"
                "1️⃣ Efectivo\n2️⃣ Tarjeta"]

    def _crear_pedido(self) -> int | None:
        items     = self._state["items"]
        cliente   = self._get_cliente()
        total     = sum(i["subtotal"] for i in items)
        nombre_c  = cliente["nombre"] if cliente else self.numero
        suc_id    = self._state.get("sucursal_id", 1)
        hora      = self._state.get("hora_deseada", "")
        prioridad = self._state.get("prioridad", "normal")
        try:
            with transaction(self.conn) as c:
                pid = c.execute("""
                    INSERT INTO pedidos_whatsapp
                        (uuid,numero_whatsapp,cliente_id,cliente_nombre,
                         estado,subtotal,total,leido,hora_deseada,prioridad,sucursal_id,fecha)
                    VALUES(lower(hex(randomblob(16))),?,?,?,'nuevo',?,?,0,?,?,?,datetime('now'))
                """, (self.numero, cliente["id"] if cliente else None,
                      nombre_c, total, total, hora, prioridad, suc_id)
                ).lastrowid
                for item in items:
                    c.execute("""
                        INSERT INTO pedidos_whatsapp_items
                            (pedido_id,producto_id,nombre_producto,
                             cantidad_pedida,precio_unitario,subtotal,unidad)
                        VALUES(?,?,?,?,?,?,'kg')
                    """, (pid, item.get("producto_id"), item["nombre_producto"],
                          item["cantidad_pedida"], item["precio_unitario"], item["subtotal"]))
            # v13.1: Publish PEDIDO_NUEVO via EventBus (non-blocking)
            try:
                from core.events.event_bus import get_bus, PEDIDO_NUEVO
                get_bus().publish(PEDIDO_NUEVO, {
                    "pedido_id":   pid,
                    "sucursal_id": suc_id,
                    "telefono":    self.numero,
                    "total":       total,
                    "hora_deseada": hora,
                    "programado":  self._state.get("programado", False),
                    "numero":      str(pid),
                }, async_=True)
            except Exception as _eb_e:
                logger.debug("EventBus PEDIDO_NUEVO bot: %s", _eb_e)
            return pid
        except Exception as e:
            logger.error("_crear_pedido: %s", e)
            return None

    def _get_total_pedido(self) -> float:
        pid = self._state.get("pedido_id")
        if not pid: return 0.0
        row = self.conn.execute(
            "SELECT total FROM pedidos_whatsapp WHERE id=?", (pid,)
        ).fetchone()
        return float(row[0]) if row else 0.0

    def _finalizar_pedido(self):
        pid = self._state.get("pedido_id")
        if not pid: return
        self.conn.execute("""
            UPDATE pedidos_whatsapp
            SET tipo_entrega=?, forma_pago=?,
                estado='confirmado', fecha_confirmacion=datetime('now')
            WHERE id=?
        """, (self._state.get("tipo_entrega"),
              self._state.get("forma_pago"), pid))
        try: self.conn.commit()
        except Exception: pass
        self._state["paso"] = "completado"
        self._save_state()

    def _get_cliente(self) -> dict | None:
        row = self.conn.execute(
            "SELECT id, nombre, puntos, nivel_fidelidad FROM clientes "
            "WHERE telefono=? AND activo=1", (self.numero,)
        ).fetchone()
        return dict(row) if row else None

    def _get_menu(self) -> str:
        try:
            rows = self.conn.execute(
                "SELECT nombre, precio, unidad FROM productos "
                "WHERE activo=1 ORDER BY categoria, nombre LIMIT 25"
            ).fetchall()
            lines = ["📋 *Menú SPJ*\n"]
            for r in rows:
                un = r[2] or "kg"
                lines.append(f"• {r[0]} — ${float(r[1]):.2f}/{un}")
            lines.append("\nEscribe tu pedido o COTIZAR para presupuesto.")
            return "\n".join(lines)
        except Exception:
            return "No pude obtener el menú en este momento."

    def _get_puntos(self) -> str:
        cliente = self._get_cliente()
        if not cliente:
            return ("No encontré tu cuenta. Registra tu número en sucursal "
                    "para acumular puntos. 🎁")
        return (f"🎁 *Tus puntos de fidelidad:*\n\n"
                f"👤 {cliente['nombre']}\n"
                f"⭐ Nivel: {cliente.get('nivel_fidelidad','Bronce')}\n"
                f"🏆 Puntos: *{int(cliente['puntos']):,}*\n\n"
                "¡Sigue comprando para subir de nivel!")

    def _try_rasa(self, texto: str):
        try:
            row = self.conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='rasa_url'"
            ).fetchone()
            if not row or not row[0]: return None
            import urllib.request
            url = row[0].rstrip("/") + "/webhooks/rest/webhook"
            payload = json.dumps({"sender": self.numero, "message": texto}).encode()
            req = urllib.request.Request(url, data=payload,
                                          headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=0.5)  # v13.1: reduced from 5s
            data = json.loads(resp.read())
            if data:
                return [m.get("text", "") for m in data if m.get("text")]
        except Exception:
            pass
        return None
