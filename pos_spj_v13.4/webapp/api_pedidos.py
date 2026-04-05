
# webapp/api_pedidos.py — SPJ POS v11
"""
API REST para la WebApp móvil de compras remotas por QR.
Puerto 8769. Sirve los archivos estáticos y expone los endpoints.
"""
from __future__ import annotations
import json, os, threading, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("spj.webapp")
_DB_PATH = "data/spj.db"


class WebAppHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        static_files = {
            "/":              ("webapp/index.html", "text/html; charset=utf-8"),
            "/index.html":    ("webapp/index.html", "text/html; charset=utf-8"),
            "/scanner_qr.js": ("webapp/scanner_qr.js", "application/javascript"),
            "/carrito.js":    ("webapp/carrito.js", "application/javascript"),
        }
        if path in static_files:
            fname, ctype = static_files[path]
            try:
                with open(fname, "rb") as f: body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
        elif path == "/api/productos":
            self._json(200, self._get_productos())
        elif path == "/api/sucursales":
            self._json(200, self._get_sucursales())
        elif path == "/api/qr":
            params = parse_qs(urlparse(self.path).query)
            uuid_qr = params.get("uuid", [""])[0]
            self._json(200, self._get_qr_info(uuid_qr))
        else:
            self.send_response(404); self.end_headers()

    def _check_auth(self) -> bool:
        """Check X-API-Token header. Skip if no token configured (dev mode)."""
        expected = self._get_config("webapp_api_token", "")
        if not expected:
            return True  # dev mode — no token configured
        return self.headers.get("X-API-Token", "") == expected

    def do_POST(self):
        if not self._check_auth():
            self._json(401, {"ok": False, "error": "No autorizado"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        path   = self.path.split("?")[0].rstrip("/")
        if path == "/api/pedido":
            result = self._crear_pedido_webapp(body)
            self._json(200 if result.get("ok") else 400, result)
        elif path == "/api/carrito/calcular":
            result = self._calcular_carrito(body)
            self._json(200, result)
        else:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _get_productos(self) -> list:
        import sqlite3
        try:
            conn = sqlite3.connect(_DB_PATH); conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, nombre, precio, existencia, categoria, unidad
                FROM productos WHERE activo=1 AND existencia>0
                ORDER BY categoria, nombre LIMIT 100""").fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("get_productos: %s", e); return []

    def _get_sucursales(self) -> list:
        import sqlite3
        try:
            conn = sqlite3.connect(_DB_PATH); conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, nombre, direccion, telefono FROM sucursales WHERE activa=1"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return [{"id":1,"nombre":"Sucursal Principal","direccion":"","telefono":""}]

    def _get_qr_info(self, uuid_qr: str) -> dict:
        import sqlite3
        try:
            conn = sqlite3.connect(_DB_PATH); conn.row_factory = sqlite3.Row
            row  = conn.execute(
                "SELECT * FROM trazabilidad_qr WHERE uuid_qr=?", (uuid_qr,)).fetchone()
            conn.close()
            if not row: return {"ok": False, "error": "QR no encontrado"}
            r = dict(row)
            if r.get("producto_id"):
                conn2 = sqlite3.connect(_DB_PATH); conn2.row_factory = sqlite3.Row
                p = conn2.execute(
                    "SELECT nombre, precio FROM productos WHERE id=?",
                    (r["producto_id"],)).fetchone()
                conn2.close()
                if p: r["producto_nombre"] = p["nombre"]; r["precio"] = float(p["precio"])
            return {"ok": True, "qr": r}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _calcular_carrito(self, body: dict) -> dict:
        items   = body.get("items", [])
        subtotal= sum(float(i.get("precio",0)) * float(i.get("cantidad",0)) for i in items)
        return {"subtotal": round(subtotal,2), "total": round(subtotal,2), "items": items}

    def _crear_pedido_webapp(self, body: dict) -> dict:
        """v13.2: uses ProcesarPedidoWAUC — audit, EventBus, anticipo."""
        try:
            from core.use_cases.pedido_wa import ProcesarPedidoWAUC, ItemPedido
            from core.db.connection import get_connection
            conn = get_connection()
            items = [
                ItemPedido(
                    producto_id = int(i.get("id", i.get("producto_id", 0))),
                    nombre      = str(i.get("nombre", "")),
                    cantidad    = float(i.get("cantidad", 1)),
                    precio      = float(i.get("precio", 0)),
                )
                for i in body.get("items", [])
                if i.get("id") or i.get("producto_id")
            ]
            if not items:
                return {"ok": False, "error": "Pedido sin items válidos"}

            uc = ProcesarPedidoWAUC(db=conn)
            r  = uc.ejecutar(
                items        = items,
                cliente_tel  = str(body.get("numero_whatsapp", "")),
                sucursal_id  = int(body.get("sucursal_id", 1)),
                usuario      = "webapp",
                notas        = body.get("notas", ""),
            )
            return {
                "ok":       r.ok,
                "pedido_id": r.pedido_id,
                "numero":   r.numero_pedido,
                "total":    r.total,
                "anticipo": r.anticipo,
                "mensaje":  r.mensaje_cliente,
                "error":    r.error,
            }
        except Exception as e:
            import logging; logging.getLogger("spj.webapp").error("_crear_pedido_webapp: %s", e)
            return {"ok": False, "error": str(e)}

    def _json(self, code: int, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def start_webapp_server(port: int = 8769, db_path: str = "data/spj.db"):
    global _DB_PATH; _DB_PATH = _DB_PATH
    server = HTTPServer(("0.0.0.0", port), WebAppHandler)
    t = threading.Thread(target=server.serve_forever,
                         daemon=True, name="WebAppServer")
    t.start()
    logger.info("WebApp móvil en http://0.0.0.0:%d", port)
    return server
