
# services/mercado_pago_service.py — SPJ POS v11
"""
Integración con MercadoPago — links de pago y webhooks.
Endpoints usados:
  POST /checkout/preferences   → crea preferencia (link de pago)
  GET  /v1/payments/{id}       → verifica estado del pago
  POST /webhook                → recibe notificaciones (desde nuestro servidor)
"""
from __future__ import annotations
import json, logging, threading, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.mercadopago")

MP_BASE = "https://api.mercadopago.com"


class MercadoPagoService:
    def __init__(self, conn=None):
        self.conn  = conn or get_connection()
        self._token = self._get_token()

    def _get_token(self) -> str:
        try:
            row = self.conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='mp_access_token'").fetchone()
            return row[0] if row else ""
        except Exception:
            return ""

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": str(uuid.uuid4()),
        }

    # ── Crear link de pago ──────────────────────────────────────────
    def crear_link(self, total: float, pedido_id: int = None,
                   descripcion: str = "Compra SPJ POS",
                   cliente_email: str = None) -> str | None:
        """Crea preferencia de pago y retorna la URL de pago."""
        if not self._token:
            logger.warning("MP: sin token configurado")
            return self._link_sandbox(total, pedido_id)

        payload = {
            "items": [{
                "id":          str(pedido_id or "0"),
                "title":       descripcion,
                "quantity":    1,
                "currency_id": "MXN",
                "unit_price":  round(float(total), 2),
            }],
            "external_reference": str(pedido_id or "0"),
            "notification_url":   self._get_webhook_url(),
            "back_urls": {
                "success": self._get_return_url("success"),
                "failure": self._get_return_url("failure"),
                "pending": self._get_return_url("pending"),
            },
            "auto_return": "approved",
        }
        if cliente_email:
            payload["payer"] = {"email": cliente_email}

        try:
            import urllib.request
            data = json.dumps(payload).encode()
            req  = urllib.request.Request(
                f"{MP_BASE}/checkout/preferences",
                data=data,
                headers=self._headers())
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            url  = resp.get("init_point") or resp.get("sandbox_init_point")
            pref_id = resp.get("id")
            if url and pedido_id:
                self._guardar_link(pedido_id, total, pref_id, url)
            logger.info("MP link creado: pedido=%s url=%s", pedido_id, url[:60] if url else "none")
            return url
        except Exception as e:
            logger.error("MP crear_link: %s", e)
            return None

    def _link_sandbox(self, total: float, pedido_id) -> str:
        """Retorna un link simulado para pruebas sin token."""
        url = f"https://www.mercadopago.com.mx/checkout/v1/redirect?pref_id=TEST_{pedido_id}_{total:.0f}"
        if pedido_id:
            self._guardar_link(pedido_id, total, f"TEST_{pedido_id}", url)
        return url

    def _guardar_link(self, pedido_id: int, monto: float,
                       preference_id: str, url: str):
        try:
            self.conn.execute("""INSERT OR REPLACE INTO links_pago
                (pedido_id, monto, preference_id, url_pago, estado)
                VALUES(?,?,?,?,'pendiente')""",
                (pedido_id, monto, preference_id, url))
            self.conn.commit()
        except Exception: pass

    # ── Verificar pago ──────────────────────────────────────────────
    def verificar_pago(self, payment_id: str) -> dict:
        if not self._token:
            return {"status": "unknown", "status_detail": "no_token"}
        try:
            import urllib.request
            req  = urllib.request.Request(
                f"{MP_BASE}/v1/payments/{payment_id}",
                headers=self._headers())
            resp = json.loads(urllib.request.urlopen(req, timeout=8).read())
            return {
                "status":         resp.get("status"),
                "status_detail":  resp.get("status_detail"),
                "amount":         resp.get("transaction_amount"),
                "external_ref":   resp.get("external_reference"),
                "payment_method": resp.get("payment_method_id"),
            }
        except Exception as e:
            logger.error("MP verificar_pago: %s", e)
            return {"status": "error", "error": str(e)}

    def procesar_webhook(self, data: dict) -> bool:
        """Procesa notificación entrante de MercadoPago."""
        tipo      = data.get("type")
        action    = data.get("action")
        payment_id = str(data.get("data", {}).get("id", ""))
        if tipo != "payment" or not payment_id:
            return False
        info = self.verificar_pago(payment_id)
        if info.get("status") == "approved":
            external_ref = info.get("external_ref")
            if external_ref:
                try:
                    pedido_id = int(external_ref)
                    with transaction(self.conn) as c:
                        c.execute("""UPDATE pedidos_whatsapp
                            SET pago_confirmado=1, estado='confirmado',
                                forma_pago='link_pago'
                            WHERE id=?""", (pedido_id,))
                        c.execute("""UPDATE links_pago
                            SET estado='pagado', payment_id=?, fecha_pago=datetime('now')
                            WHERE pedido_id=?""", (payment_id, pedido_id))
                    logger.info("MP pago aprobado: pedido=%d payment=%s",
                                pedido_id, payment_id)
                    return True
                except Exception as e:
                    logger.error("procesar_webhook BD: %s", e)
        return False

    def _get_webhook_url(self) -> str:
        try:
            row = self.conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='mp_webhook_url'").fetchone()
            return row[0] if row else ""
        except Exception:
            return ""

    def _get_return_url(self, status: str) -> str:
        try:
            row = self.conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='mp_return_url'").fetchone()
            base = row[0] if row else "http://localhost:8765"
            return f"{base}/pago/{status}"
        except Exception:
            return f"http://localhost:8765/pago/{status}"


class MPWebhookHandler(BaseHTTPRequestHandler):
    svc: MercadoPagoService = None
    on_pago_aprobado = None   # callback(pedido_id)

    def log_message(self, *a): pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        self.send_response(200); self.end_headers()
        try:
            data = json.loads(body)
            ok   = self.svc.procesar_webhook(data) if self.svc else False
            if ok and self.on_pago_aprobado:
                try:
                    ext = str(data.get("data", {}).get("id", ""))
                    self.on_pago_aprobado(ext)
                except Exception: pass
        except Exception as e:
            logger.error("MP webhook handler: %s", e)


class MPWebhookServer:
    def __init__(self, port: int = 8768, svc: MercadoPagoService = None,
                 on_pago_aprobado=None):
        self.port = port
        MPWebhookHandler.svc              = svc
        MPWebhookHandler.on_pago_aprobado = on_pago_aprobado

    def start(self):
        server = HTTPServer(("0.0.0.0", self.port), MPWebhookHandler)
        t = threading.Thread(target=server.serve_forever,
                             daemon=True, name="MPWebhook")
        t.start()
        logger.info("MercadoPago webhook en puerto %d", self.port)
