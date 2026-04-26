
# webapp/api_pedidos.py — SPJ POS v13.4
"""
API REST para la WebApp móvil + Dashboard Web.
Puerto 8769. Sirve los archivos estáticos y expone los endpoints.

Endpoints estáticos:
    /                         → webapp/index.html  (nueva UI web)
    /index.html               → webapp/index.html
    /static/css/*             → webapp/static/css/*
    /static/js/*              → webapp/static/js/*
    /scanner_qr.js            → webapp/scanner_qr.js  (legacy)
    /carrito.js               → webapp/carrito.js     (legacy)

Endpoints API:
    GET  /api/productos
    GET  /api/sucursales
    GET  /api/qr?uuid=...
    POST /api/pedido
    POST /api/carrito/calcular
    GET  /api/dashboard/kpis
    GET  /api/dashboard/ventas-chart
    GET  /api/dashboard/productos-top
    GET  /api/dashboard/inventario
    GET  /api/dashboard/alertas
"""
from __future__ import annotations
import json, os, mimetypes, threading, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import sqlite3

logger = logging.getLogger("spj.webapp")
_DB_PATH = "data/spj.db"
_CORS_ORIGIN = os.getenv("SPJ_WEBAPP_CORS_ORIGIN", "http://localhost")


def _record_security_event(action: str, detail: str = "", ip: str = "") -> None:
    """
    Registra eventos de seguridad de WebApp (best-effort).
    No bloquea la operación principal si falla.
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO audit_logs
            (usuario, accion, modulo, entidad, entidad_id, valor_antes, valor_despues, sucursal_id, detalles)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "webapp",
                action,
                "WEBAPP",
                "AUTH",
                ip or "0.0.0.0",
                "{}",
                "{}",
                1,
                detail or "",
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("No se pudo registrar evento de seguridad WebApp: %s", e)


class WebAppHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    # ── Base dir para archivos estáticos ──────────────────────────────────
    _WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))

    # Tipos MIME adicionales para archivos web
    _EXTRA_MIME = {
        ".css":  "text/css; charset=utf-8",
        ".js":   "application/javascript; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json",
        ".svg":  "image/svg+xml",
        ".ico":  "image/x-icon",
        ".png":  "image/png",
        ".woff2": "font/woff2",
    }

    def _serve_static(self, rel_path: str) -> bool:
        """
        Sirve un archivo estático desde _WEBAPP_DIR.
        Retorna True si se sirvió, False si no se encontró.
        """
        abs_path = os.path.normpath(os.path.join(self._WEBAPP_DIR, rel_path))
        # Seguridad: no salir del directorio webapp
        if not abs_path.startswith(self._WEBAPP_DIR):
            self.send_response(403); self.end_headers()
            return True
        if not os.path.isfile(abs_path):
            return False
        ext = os.path.splitext(abs_path)[1].lower()
        ctype = self._EXTRA_MIME.get(ext) or mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
        try:
            with open(abs_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(body)
            return True
        except OSError:
            return False

    def do_GET(self):
        parsed   = urlparse(self.path)
        path     = parsed.path.rstrip("/") or "/"
        qs       = parse_qs(parsed.query)

        # ── Archivos estáticos de la nueva UI ──────────────────────────────
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return

        # /static/css/* y /static/js/*
        if path.startswith("/static/"):
            rel = path.lstrip("/")  # static/css/tokens.css
            if not self._serve_static(rel):
                self.send_response(404); self.end_headers()
            return

        # Archivos legacy
        _legacy = {
            "/scanner_qr.js": "scanner_qr.js",
            "/carrito.js":    "carrito.js",
        }
        if path in _legacy:
            if not self._serve_static(_legacy[path]):
                self.send_response(404); self.end_headers()
            return

        # ── Endpoints API — requieren auth ─────────────────────────────────
        if path.startswith("/api/") and not self._check_auth():
            _record_security_event(
                "WEBAPP_AUTH_DENIED_GET",
                detail=f"Ruta: {path}",
                ip=(self.client_address[0] if self.client_address else ""),
            )
            self._json(401, {"ok": False, "error": "No autorizado"})
            return

        # Dashboard endpoints
        if path.startswith("/api/dashboard/"):
            try:
                from webapp.api_dashboard import DASHBOARD_ROUTES
                handler = DASHBOARD_ROUTES.get(path)
                if handler:
                    params = {k: v[0] for k, v in qs.items()}
                    self._json(200, handler(params))
                else:
                    self._json(404, {"ok": False, "error": "Endpoint no encontrado"})
            except Exception as e:
                logger.error("dashboard handler error: %s", e)
                self._json(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/productos":
            self._json(200, self._get_productos())
        elif path == "/api/sucursales":
            self._json(200, self._get_sucursales())
        elif path == "/api/qr":
            uuid_qr = qs.get("uuid", [""])[0]
            self._json(200, self._get_qr_info(uuid_qr))
        else:
            self.send_response(404); self.end_headers()

    def _check_auth(self) -> bool:
        """Check X-API-Token header."""
        expected = self._get_config("webapp_api_token", "")
        if not expected:
            logger.error("WebApp API sin token configurado; acceso denegado.")
            return False
        return self.headers.get("X-API-Token", "") == expected

    def do_POST(self):
        if not self._check_auth():
            _record_security_event(
                "WEBAPP_AUTH_DENIED_POST",
                detail=f"Ruta: {self.path}",
                ip=(self.client_address[0] if self.client_address else ""),
            )
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
        self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Token")
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
        self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
        self.end_headers()
        self.wfile.write(body)


def start_webapp_server(port: int = 8769, db_path: str = "data/spj.db"):
    global _DB_PATH
    _DB_PATH = db_path
    server = HTTPServer(("0.0.0.0", port), WebAppHandler)
    t = threading.Thread(target=server.serve_forever,
                         daemon=True, name="WebAppServer")
    t.start()
    logger.info("WebApp móvil en http://0.0.0.0:%d", port)
    return server
