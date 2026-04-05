
# integrations/delivery_pwa/pwa_server.py — SPJ POS v9
"""
Mini servidor HTTP local para la PWA de repartidores.
Corre en un hilo daemon. Los repartidores acceden con su
celular a http://192.168.x.x:8765
"""
from __future__ import annotations
import json, threading, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from core.db.connection import get_connection, close_thread_connection

logger = logging.getLogger("spj.pwa")
_server_instance = None


class DeliveryAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # silenciar logs HTTP

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/" or path == "/index.html":
            self._send_html(_PWA_HTML)
        elif path == "/api/pedidos":
            params = parse_qs(parsed.query)
            token  = params.get('token',[''])[0]
            chofer = _validate_token(token) or params.get('chofer',[''])[0]
            self._send_json(self._get_pedidos(chofer))
        elif path == "/manifest.json":
            self._send_json(_MANIFEST)
        elif path == "/sw.js":
            self.send_response(200)
            self.send_header("Content-type","application/javascript")
            self.end_headers()
            self.wfile.write(_SW_JS.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length  = int(self.headers.get("Content-Length",0))
        body    = json.loads(self.rfile.read(length)) if length else {}
        parsed  = urlparse(self.path)

        if parsed.path == "/api/estado":
            ok = self._actualizar_estado(body)
            self._send_json({"ok": ok})
        elif parsed.path == "/api/ubicacion":
            ok = self._guardar_ubicacion(body)
            self._send_json({"ok": ok})
        else:
            self.send_response(404); self.end_headers()

    def _get_pedidos(self, chofer_id: str) -> list:
        try:
            conn = get_connection()
            sql  = """SELECT d.id, d.estado, d.direccion_entrega, d.notas,
                             d.total, d.fecha_pedido,
                             c.nombre as cliente, c.telefono as tel_cliente
                      FROM delivery_orders d
                      LEFT JOIN clientes c ON c.id=d.cliente_id
                      WHERE d.estado NOT IN ('entregado','cancelado')"""
            params = []
            if chofer_id:
                sql += " AND d.chofer_id=?"; params.append(chofer_id)
            sql += " ORDER BY d.fecha_pedido ASC LIMIT 50"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_pedidos: %s", e)
            return []

    def _actualizar_estado(self, body: dict) -> bool:
        try:
            conn     = get_connection()
            pedido_id = body.get("id")
            estado   = body.get("estado")
            if not pedido_id or not estado:
                return False
            conn.execute(
                "UPDATE delivery_orders SET estado=? WHERE id=?",
                (estado, pedido_id))
            try: conn.commit()
            except Exception: pass
            logger.info("PWA: pedido %s -> %s", pedido_id, estado)
            return True
        except Exception as e:
            logger.warning("actualizar_estado: %s", e)
            return False

    def _guardar_ubicacion(self, body: dict) -> bool:
        try:
            conn = get_connection()
            conn.execute("""INSERT OR REPLACE INTO driver_locations
                (chofer_id, lat, lng, timestamp) VALUES(?,?,?,datetime('now'))""",
                (body.get("chofer_id"), body.get("lat"), body.get("lng")))
            try:
                conn.execute("""CREATE TABLE IF NOT EXISTS driver_locations(
                    chofer_id INTEGER PRIMARY KEY, lat REAL, lng REAL,
                    timestamp DATETIME)""")
                conn.commit()
            except Exception: pass
            return True
        except Exception: return False

    def _send_json(self, data):
        body = json.dumps(data, default=str, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)



import secrets, hashlib

_TOKENS: dict = {}  # token -> {chofer_id, expires}

def _generate_token(chofer_id: str) -> str:
    token = secrets.token_urlsafe(32)
    import time
    _TOKENS[token] = {"chofer_id": chofer_id, "expires": time.time() + 86400}
    return token

def _validate_token(token: str) -> str | None:
    import time
    info = _TOKENS.get(token)
    if not info: return None
    if time.time() > info["expires"]:
        _TOKENS.pop(token, None); return None
    return info["chofer_id"]

_MANIFEST = {
    "name": "SPJ Delivery",
    "short_name": "Delivery",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0F172A",
    "theme_color": "#3B82F6",
    "icons": [{"src":"data:image/svg+xml,<svg/>","sizes":"192x192","type":"image/svg+xml"}]
}

_SW_JS = """
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => clients.claim());
self.addEventListener('fetch', e => e.respondWith(fetch(e.request).catch(() => caches.match(e.request))));
"""

_PWA_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#3B82F6">
<link rel="manifest" href="/manifest.json">
<title>SPJ Delivery</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0F172A;color:#E2E8F0;min-height:100vh}
  header{background:#1E3A5F;padding:16px;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:18px;font-weight:700;color:#60A5FA}
  #chofer-input{background:#334155;color:#E2E8F0;border:none;border-radius:8px;padding:8px 12px;font-size:14px}
  #pedidos{padding:12px;display:flex;flex-direction:column;gap:12px}
  .card{background:#1E293B;border-radius:12px;padding:16px;border-left:4px solid #3B82F6}
  .card.en_camino{border-color:#F59E0B}
  .card.listo{border-color:#10B981}
  .card h3{font-size:15px;font-weight:600;margin-bottom:4px}
  .card .addr{color:#94A3B8;font-size:13px;margin-bottom:8px}
  .card .meta{display:flex;justify-content:space-between;font-size:12px;color:#64748B;margin-bottom:10px}
  .btns{display:flex;gap:8px;flex-wrap:wrap}
  .btn{padding:8px 14px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;flex:1}
  .btn-camino{background:#F59E0B;color:#000}
  .btn-entregado{background:#10B981;color:#fff}
  .btn-problema{background:#EF4444;color:#fff}
  .badge{display:inline-block;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:600;margin-bottom:6px}
  .badge.pendiente{background:#334155;color:#94A3B8}
  .badge.listo{background:#064E3B;color:#10B981}
  .badge.en_camino{background:#451A03;color:#F59E0B}
  #empty{text-align:center;color:#64748B;padding:48px;display:none}
  #refresh-btn{background:#3B82F6;color:#fff;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:14px}
</style>
</head>
<body>
<header>
  <h1>🚚 SPJ Delivery</h1>
  <div style="display:flex;gap:8px;align-items:center">
    <input id="chofer-input" placeholder="ID Repartidor" style="width:120px">
    <button id="refresh-btn" onclick="cargar()">↻</button>
  </div>
</header>
<div id="pedidos"><div id="empty">No hay pedidos asignados</div></div>
<script>
const ESTADOS = {pendiente:'Pendiente',listo:'Listo para enviar',en_camino:'En camino',entregado:'Entregado'};
let timer;

async function cargar(){
  const chofer = document.getElementById('chofer-input').value;
  try{
    const r = await fetch(`/api/pedidos?chofer=${chofer}`);
    const data = await r.json();
    renderizar(data);
  }catch(e){console.warn('Sin conexión',e)}
}

function renderizar(pedidos){
  const c = document.getElementById('pedidos');
  document.getElementById('empty').style.display = pedidos.length ? 'none' : 'block';
  c.innerHTML = '<div id="empty" style="display:'+(pedidos.length?'none':'block')+'">No hay pedidos</div>';
  pedidos.forEach(p=>{
    const div = document.createElement('div');
    div.className = `card ${p.estado}`;
    div.innerHTML = `
      <span class="badge ${p.estado}">${ESTADOS[p.estado]||p.estado}</span>
      <h3>#${p.id} — ${p.cliente||'Cliente'}</h3>
      <div class="addr">📍 ${p.direccion_entrega||'Sin dirección'}</div>
      <div class="meta">
        <span>💰 $${parseFloat(p.total||0).toFixed(2)}</span>
        <span>${p.fecha_pedido?.substring(0,16)||''}</span>
      </div>
      ${p.notas?`<div class="addr" style="color:#F59E0B">📝 ${p.notas}</div>`:''}
      <div class="btns">
        ${p.estado==='listo'?`<button class="btn btn-camino" onclick="cambiarEstado(${p.id},'en_camino')">🚚 Salir a entregar</button>`:''}
        ${p.estado==='en_camino'?`<button class="btn btn-entregado" onclick="cambiarEstado(${p.id},'entregado')">✅ Entregado</button>`:''}
        <button class="btn btn-problema" onclick="cambiarEstado(${p.id},'cancelado')" style="flex:0;padding:8px">⚠</button>
      </div>`;
    c.appendChild(div);
  });
}

async function cambiarEstado(id, estado){
  if(!confirm(`¿Cambiar pedido #${id} a "${estado}"?`)) return;
  await fetch('/api/estado',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id,estado})});
  cargar();
}

// Geolocalización periódica
if(navigator.geolocation){
  setInterval(()=>{
    const chofer = document.getElementById('chofer-input').value;
    if(!chofer) return;
    navigator.geolocation.getCurrentPosition(pos=>{
      fetch('/api/ubicacion',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({chofer_id:chofer,lat:pos.coords.latitude,lng:pos.coords.longitude})});
    });
  }, 30000);
}

// Auto-refresh cada 15 segundos
timer = setInterval(cargar, 15000);
cargar();

if('serviceWorker' in navigator)
  navigator.serviceWorker.register('/sw.js');
</script>
</body>
</html>"""


class PwaServerThread(threading.Thread):
    def __init__(self, port: int = 8765, db_path: str = None):
        super().__init__(daemon=True, name="PWAServer")
        self.port    = port
        self.DB_PATH = _DB_PATH
        self._server = None

    def run(self):
        try:
            if self.db_path:
                from core.db.connection import set_db_path
                set_db_path(self.db_path)
            self._server = HTTPServer(("0.0.0.0", self.port), DeliveryAPIHandler)
            logger.info("PWA servidor en http://0.0.0.0:%d", self.port)
            self._server.serve_forever()
        except Exception as e:
            logger.error("PWA server error: %s", e)

    def stop(self):
        if self._server:
            self._server.shutdown()
        close_thread_connection()


def start_pwa_server(port: int = 8765, db_path: str = None) -> PwaServerThread:
    global _server_instance
    if _server_instance and _server_instance.is_alive():
        return _server_instance
    _server_instance = PwaServerThread(port, db_path)
    _server_instance.start()
    return _server_instance
