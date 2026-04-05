
# core/services/whatsapp_service.py — SPJ POS v12
# ── WhatsApp Service Unificado ─────────────────────────────────────────────────
# Fusion de:
#   core/services/whatsapp_service.py  (v11 daemon-threads + feature-flags)
#   services/whatsapp_service.py       (v11 multi-proveedor + templates + webhook)
#   integrations/whatsapp_service.py   (v7  offline-first + cola persistente)
# Agrega integracion Rasa para bot conversacional.
from __future__ import annotations
import json, logging, threading, time, urllib.request
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse
from core.db.connection import get_connection
logger = logging.getLogger("spj.whatsapp")

# ─────────────────────────────────────────────────────────────────────────────
class WhatsAppConfig:
    """
    Carga configuración desde whatsapp_numeros (nuevo) o configuraciones (legacy).
    canal: 'clientes' | 'rrhh' | 'alertas' | 'todos'
    sucursal_id: None = global, N = sucursal específica
    """
    def __init__(self, conn=None, canal: str = "clientes", sucursal_id: int = None):
        c = conn or get_connection()
        self.activo = False

        # ── Intentar nuevo esquema (whatsapp_numeros) ──────────────────────
        try:
            row = None
            if sucursal_id:
                # Primero buscar config específica de sucursal
                row = c.execute("""
                    SELECT proveedor, numero_negocio, meta_token, meta_phone_id,
                           twilio_sid, twilio_token, verify_token
                    FROM whatsapp_numeros
                    WHERE canal IN (?, 'todos') AND sucursal_id=? AND activo=1
                    ORDER BY CASE WHEN canal=? THEN 0 ELSE 1 END LIMIT 1
                """, (canal, sucursal_id, canal)).fetchone()
            if not row:
                # Fallback: config global (sucursal_id IS NULL)
                row = c.execute("""
                    SELECT proveedor, numero_negocio, meta_token, meta_phone_id,
                           twilio_sid, twilio_token, verify_token
                    FROM whatsapp_numeros
                    WHERE canal IN (?, 'todos') AND sucursal_id IS NULL AND activo=1
                    ORDER BY CASE WHEN canal=? THEN 0 ELSE 1 END LIMIT 1
                """, (canal, canal)).fetchone()
            if row:
                self.proveedor      = row[0] or "meta"
                self.numero_negocio = row[1] or ""
                self.meta_token     = row[2] or ""
                self.meta_phone_id  = row[3] or ""
                self.account_sid    = row[4] or ""
                self.auth_token_tw  = row[5] or ""
                self.verify_token   = row[6] or "spj_verify"
                self.activo         = bool(self.meta_token or self.account_sid)
                self.api_url        = ""
                self.api_token      = self.meta_token
                self.rasa_url       = self._get_legacy(c, "rasa_url", "http://localhost:5005")
                return
        except Exception:
            pass

        # ── Fallback: esquema legacy (tabla configuraciones) ──────────────
        def _g(k, d=""):
            try:
                r = c.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r else d
            except Exception:
                return d

        self.numero_negocio = _g("whatsapp_numero")
        self.api_url        = _g("whatsapp_api_url")
        self.api_token      = _g("whatsapp_api_token")
        self.proveedor      = _g("whatsapp_proveedor", "meta")
        self.activo         = _g("whatsapp_enabled", "0") in ("1","true","True")
        self.meta_token     = _g("wa_meta_token")
        self.meta_phone_id  = _g("wa_meta_phone_id")
        self.verify_token   = _g("wa_verify_token", "spj_verify")
        self.account_sid    = _g("wa_account_sid")
        self.auth_token_tw  = _g("wa_auth_token")
        self.rasa_url       = _g("rasa_url", "http://localhost:5005")

    @staticmethod
    def _get_legacy(conn, clave, default=""):
        try:
            r = conn.execute("SELECT valor FROM configuraciones WHERE clave=?", (clave,)).fetchone()
            return r[0] if r else default
        except Exception:
            return default

    @classmethod
    def para_rrhh(cls, conn=None, sucursal_id: int = None) -> "WhatsAppConfig":
        """Instancia para notificaciones RRHH (usa número 'rrhh' si existe)."""
        return cls(conn=conn, canal="rrhh", sucursal_id=sucursal_id)

    @classmethod
    def para_sucursal(cls, conn=None, sucursal_id: int = 1) -> "WhatsAppConfig":
        """Instancia para notificaciones de clientes de una sucursal específica."""
        return cls(conn=conn, canal="clientes", sucursal_id=sucursal_id)

# ─────────────────────────────────────────────────────────────────────────────
class MessageQueue:
    """Cola persistente SQLite — offline-first, reintentos automaticos."""
    def __init__(self, conn=None):
        self.conn = conn or get_connection()
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                to_number TEXT NOT NULL, message TEXT NOT NULL,
                template TEXT, payload TEXT,
                estado TEXT DEFAULT 'pendiente',
                intentos INTEGER DEFAULT 0, error TEXT,
                fecha TEXT DEFAULT (datetime('now')),
                enviado_en TEXT)""")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_queue_estado ON whatsapp_queue(estado,fecha)")
        try: self.conn.commit()
        except Exception: pass

    def enqueue(self, to_number, message, template=None, payload=None):
        self.conn.execute(
            "INSERT INTO whatsapp_queue(to_number,message,template,payload) VALUES(?,?,?,?)",
            (to_number, message, template, json.dumps(payload) if payload else None))
        try: self.conn.commit()
        except Exception: pass

    def get_pending(self, limit=20):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM whatsapp_queue WHERE estado='pendiente' AND intentos<5 ORDER BY fecha LIMIT ?",
            (limit,)).fetchall()]

    def mark_sent(self, msg_id):
        self.conn.execute(
            "UPDATE whatsapp_queue SET estado='enviado',enviado_en=datetime('now') WHERE id=?",
            (msg_id,))
        try: self.conn.commit()
        except Exception: pass

    def mark_error(self, msg_id, error):
        self.conn.execute(
            "UPDATE whatsapp_queue SET intentos=intentos+1,error=?,"
            "estado=CASE WHEN intentos+1>=5 THEN 'fallido' ELSE 'pendiente' END WHERE id=?",
            (error, msg_id))
        try: self.conn.commit()
        except Exception: pass

        # S39: notificacion de fallidos implementada via scheduler check

# ─────────────────────────────────────────────────────────────────────────────
class WhatsAppService:
    """
    Servicio WhatsApp unificado SPJ v12.
    Soporta: Meta Cloud API / Twilio / mock.
    Cola persistente offline-first con worker daemon.
    Integracion con Rasa para bot conversacional.
    """
    TEMPLATES = {
        "bienvenida":         "Hola {nombre}! Bienvenido a SPJ.",
        "pedido_recibido":    "Tu pedido #{folio} fue recibido. Total: ${total}.",
        "pedido_listo":       "{nombre}, pedido #{folio} LISTO.",
        "delivery_en_camino": "{nombre}, pedido en camino. Rep: {repartidor}. ~{tiempo}min.",
        "delivery_entregado": "Pedido {folio} entregado. Gracias {nombre}!",
        "puntos_ganados":     "{nombre}, ganaste {puntos} pts. Total: {total_puntos} pts.",
        "nivel_subido":       "{nombre} sube a nivel {nivel}!",
        "promo_especial":     "{nombre}: {descripcion}. Hasta {fecha_fin}.",
        "ticket_digital":     "Ticket {fecha}: {detalle} | Total: ${total}",
        "link_pago":          "Paga ${total:.2f}: {url}",
        "pago_confirmado":    "Pago OK — Pedido #{folio} en camino.",
    }

    def __init__(self, conn=None, api_url=None, api_token=None, feature_service=None):
        self.conn = conn or get_connection()
        self.config = WhatsAppConfig(self.conn)
        self.queue = MessageQueue(self.conn)
        self.feature_service = feature_service
        self._worker_thread = None
        if api_url: self.config.api_url = api_url
        if api_token: self.config.api_token = api_token

    # ── Envio principal ───────────────────────────────────────────────────────
    def send_message(self, branch_id=None, phone_number="", message="",
                     to=None, body=None):
        destino = phone_number or to or ""
        contenido = message or body or ""
        if self.feature_service and branch_id:
            if not self.feature_service.is_enabled("whatsapp_notifications", branch_id):
                return
        if not destino or not contenido:
            return
        clean = "".join(filter(str.isdigit, str(destino)))
        self.queue.enqueue(clean, contenido)
        self._ensure_worker()

    # ── Notificaciones de negocio ─────────────────────────────────────────────
    def notificar_pedido(self, telefono, nombre, folio, total):
        self.queue.enqueue(telefono, self._render("pedido_recibido", nombre=nombre, folio=folio, total=f"{total:.2f}"))
        self._ensure_worker()

    def notificar_delivery_en_camino(self, telefono, nombre, folio, repartidor, tiempo_min=30):
        self.queue.enqueue(telefono, self._render("delivery_en_camino", nombre=nombre, folio=folio, repartidor=repartidor, tiempo=tiempo_min))
        self._ensure_worker()

    def notificar_delivery_entregado(self, telefono, nombre, folio):
        self.queue.enqueue(telefono, self._render("delivery_entregado", nombre=nombre, folio=folio))
        self._ensure_worker()

    def notificar_puntos(self, telefono, nombre, puntos, total_puntos):
        self.queue.enqueue(telefono, self._render("puntos_ganados", nombre=nombre, puntos=puntos, total_puntos=total_puntos))
        self._ensure_worker()

    def notificar_nivel(self, telefono, nombre, nivel):
        self.queue.enqueue(telefono, self._render("nivel_subido", nombre=nombre, nivel=nivel))
        self._ensure_worker()

    def enviar_promo(self, telefono, nombre, descripcion, fecha_fin=""):
        self.queue.enqueue(telefono, self._render("promo_especial", nombre=nombre, descripcion=descripcion, fecha_fin=fecha_fin))
        self._ensure_worker()

    def enviar_ticket_digital(self, telefono, ticket_data):
        detalle = "\n".join(f"  {i[0]} x{i[1]}=${i[1]*i[2]:.2f}" for i in ticket_data.get("items",[]))
        msg = self._render("ticket_digital", fecha=datetime.now().strftime("%d/%m/%Y %H:%M"),
                           detalle=detalle, total=ticket_data.get("total",0))
        tel = ticket_data.get("telefono", telefono)
        if tel: self.queue.enqueue(tel, msg); self._ensure_worker()

    def enviar_bienvenida(self, telefono, nombre):
        self.queue.enqueue(telefono, self._render("bienvenida", nombre=nombre))
        self._ensure_worker()

    def send_payment_link(self, branch_id, phone, order_id, amount):
        url = f"https://pay.spjpos.com/{order_id}"
        self.send_message(branch_id=branch_id, phone_number=phone,
                         message=self._render("link_pago", url=url, total=amount))

    def send_psychological_message(self, branch_id, phone, context):
        msgs = {"gamification": "Cada pedido te acerca a tu recompensa.",
                "loyalty": "Sigue acumulando puntos para subir de nivel.",
                "promo": "Revisa nuestras ofertas en sucursal!"}
        self.send_message(branch_id=branch_id, phone_number=phone,
                         message=msgs.get(context, "Gracias por elegir SPJ!"))

    # ── Rasa integration ──────────────────────────────────────────────────────
    def forward_to_rasa(self, sender_id, message):
        """Envia mensaje al bot Rasa (puerto 5005). Fallback local si no disponible."""
        try:
            import requests
            resp = requests.post(
                f"{self.config.rasa_url}/webhooks/rest/webhook",
                json={"sender": sender_id, "message": message}, timeout=10)
            responses = resp.json()
            texts = [r.get("text","") for r in responses if r.get("text")]
            return " ".join(texts) if texts else ""
        except Exception as e:
            logger.warning("Rasa no disponible: %s", e)
            return self.procesar_mensaje_local(sender_id, message)

    def procesar_mensaje_local(self, from_number, body):
        """Respuestas simples cuando Rasa no esta disponible."""
        b = body.strip().lower()
        if b in ("hola","hi","hello","buenos dias","buenas"):
            return self._render("bienvenida", nombre="Cliente")
        if "pedido" in b or "orden" in b:
            return "Para pedir escribe: PEDIR [producto] [cantidad]. Ej: PEDIR pollo 2kg"
        if b.startswith("pedir "):
            return "Pedido recibido! Un asesor te contactara pronto."
        if "puntos" in b: return "Consulta tus puntos con el cajero."
        if "promo" in b or "oferta" in b:
            try:
                r = self.conn.execute("SELECT mensaje FROM marketing_messages WHERE contexto='whatsapp' AND activo=1 ORDER BY prioridad DESC LIMIT 1").fetchone()
                return r[0] if r else "Consulta nuestras promociones en sucursal."
            except Exception: return "Consulta nuestras promociones en sucursal."
        return None

    # ── Worker ────────────────────────────────────────────────────────────────
    def _ensure_worker(self):
        if self._worker_thread and self._worker_thread.is_alive(): return
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="WA-Worker")
        self._worker_thread.start()

    def start_worker(self): self._ensure_worker()

    def _worker_loop(self):
        while True:
            try:
                for msg in self.queue.get_pending():
                    ok, err = self._send_api(msg["to_number"], msg["message"])
                    if ok: self.queue.mark_sent(msg["id"])
                    else: self.queue.mark_error(msg["id"], err)
            except Exception as e: logger.warning("WA worker: %s", e)
            time.sleep(60)

    # ── API providers ─────────────────────────────────────────────────────────
    def _send_api(self, to, message):
        if not self.config.activo:
            logger.debug("[WA MOCK -> %s]: %s", to, message[:60])
            return True, ""
        return self._send_twilio(to, message) if self.config.proveedor=="twilio" else self._send_meta(to, message)

    def _send_meta(self, to, body):
        try:
            token = self.config.meta_token or self.config.api_token
            phone_id = self.config.meta_phone_id
            url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
            data = json.dumps({"messaging_product":"whatsapp","to":to.replace("+",""),
                               "type":"text","text":{"body":body}}).encode()
            req = urllib.request.Request(url, data=data,
                    headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status in (200,201,202), ""
        except Exception as e:
            logger.error("Meta WA: %s", e); return False, str(e)

    def _send_twilio(self, to, body):
        try:
            from twilio.rest import Client
            c = Client(self.config.account_sid, self.config.auth_token_tw)
            c.messages.create(from_=f"whatsapp:{self.config.numero_negocio}",
                              to=f"whatsapp:{to}" if not to.startswith("whatsapp:") else to,
                              body=body)
            return True, ""
        except ImportError: return self._send_meta(to, body)
        except Exception as e: logger.error("Twilio: %s", e); return False, str(e)

    def _render(self, key, **kwargs):
        tpl = self.TEMPLATES.get(key, "{mensaje}")
        try:
            r = self.conn.execute("SELECT mensaje FROM marketing_messages WHERE nombre=? AND activo=1",(key,)).fetchone()
            if r: tpl = r[0]
        except Exception: pass
        try: return tpl.format(**kwargs)
        except KeyError: return tpl

    # Alias legacy
    def _ejecutar_peticion_http(self, phone_number, message):
        self.queue.enqueue(phone_number, message); self._ensure_worker()

# ─────────────────────────────────────────────────────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):
    svc: "WhatsAppService" = None
    pedido_cb = None
    def log_message(self, *a): pass

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        vt = params.get("hub.verify_token",[""])[0]
        ch = params.get("hub.challenge",[""])[0]
        exp = self.svc.config.verify_token if self.svc else ""
        if vt == exp:
            self.send_response(200); self.end_headers(); self.wfile.write(ch.encode())
        else:
            self.send_response(403); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = self.rfile.read(length)
        self.send_response(200); self.end_headers()
        try:
            data = json.loads(body)
            self._proc(data)
        except Exception as e: logger.error("Webhook: %s", e)

    def _proc(self, data):
        try:
            msg = (data.get("entry",[{}])[0].get("changes",[{}])[0]
                      .get("value",{}).get("messages",[]))
            if not msg: return
            m = msg[0]
            from_num = m.get("from","")
            texto = (m.get("text") or {}).get("body","").strip()
            if not texto: return
            resp = None
            if self.svc:
                resp = self.svc.forward_to_rasa(from_num, texto)
                if not resp: resp = self.svc.procesar_mensaje_local(from_num, texto)
                if resp: self.svc.send_message(phone_number=from_num, message=resp)
            if self.pedido_cb:
                self.pedido_cb({"numero":from_num,"texto":texto,"respuesta":resp,"timestamp":m.get("timestamp")})
        except Exception as e: logger.error("_proc: %s", e)

class WhatsAppWebhookServer:
    def __init__(self, port=8767, whatsapp_svc=None, pedido_callback=None):
        self.port=port; self._svc=whatsapp_svc; self._cb=pedido_callback; self._server=None
    def start(self):
        WebhookHandler.svc=self._svc; WebhookHandler.pedido_cb=self._cb
        self._server=HTTPServer(("0.0.0.0",self.port),WebhookHandler)
        threading.Thread(target=self._server.serve_forever,daemon=True,name="WAWebhook").start()
        logger.info("WA webhook puerto %d", self.port)
    def stop(self):
        if self._server: self._server.shutdown()
