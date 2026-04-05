
# core/health/health_server.py — SPJ POS v10
"""
Servidor HTTP de health check en puerto 8766.
  GET /health       -> {"status":"ok","db":"ok","version":"10",...}
  GET /health/db    -> Detalle de integridad de BD
  GET /health/ready -> Listo para recibir ventas (turno abierto, BD OK)
  GET /metrics      -> Metricas en formato Prometheus
"""
from __future__ import annotations
import json, time, threading, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

logger = logging.getLogger("spj.health")
_start_time = time.time()


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        {
            "/health":       self._health,
            "/health/db":    self._health_db,
            "/health/ready": self._health_ready,
            "/metrics":      self._metrics,
        }.get(path, self._not_found)()

    def _health(self):
        from core.db.connection import get_connection
        db_ok = True
        try:
            get_connection().execute("SELECT 1")
        except Exception:
            db_ok = False
        code = 200 if db_ok else 503
        self._json(code, {
            "status":   "ok" if db_ok else "degraded",
            "version":  "10",
            "uptime_s": int(time.time() - _start_time),
            "db":       "ok" if db_ok else "error",
            "ts":       datetime.utcnow().isoformat(),
        })

    def _health_db(self):
        from core.db.connection import get_connection
        from core.db.integrity import check_integrity
        try:
            conn = get_connection()
            ok, errors = check_integrity(conn)
            tables   = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            pc       = conn.execute("PRAGMA page_count").fetchone()[0]
            ps       = conn.execute("PRAGMA page_size").fetchone()[0]
            self._json(200 if ok else 503, {
                "integrity": "ok" if ok else "error",
                "errors":    errors[:5],
                "tables":    tables,
                "size_mb":   round(pc * ps / 1_048_576, 2),
            })
        except Exception as e:
            self._json(503, {"status": "error", "detail": str(e)})

    def _health_ready(self):
        from core.db.connection import get_connection
        try:
            conn  = get_connection()
            turno = conn.execute("SELECT 1 FROM turno_actual WHERE abierto=1 LIMIT 1").fetchone()
            ventas = conn.execute(
                "SELECT COUNT(*) FROM ventas WHERE DATE(fecha)=DATE('now')").fetchone()[0]
            self._json(200 if turno else 503, {
                "ready":        bool(turno),
                "turno_abierto":bool(turno),
                "ventas_hoy":   ventas,
            })
        except Exception as e:
            self._json(503, {"ready": False, "error": str(e)})

    def _metrics(self):
        from core.db.connection import get_connection
        try:
            c = get_connection()
            def q(sql):
                try: return c.execute(sql).fetchone()[0] or 0
                except Exception: return 0
            ventas = q("SELECT COUNT(*) FROM ventas WHERE DATE(fecha)=DATE('now') AND estado='completada'")
            total  = float(q("SELECT COALESCE(SUM(total),0) FROM ventas WHERE DATE(fecha)=DATE('now') AND estado='completada'"))
            bajo   = q("SELECT COUNT(*) FROM productos WHERE existencia<=stock_minimo AND activo=1")
            up     = int(time.time()-_start_time)
            body   = (
                "# HELP spj_ventas_hoy Ventas completadas hoy\n"
                f"spj_ventas_hoy {ventas}\n"
                "# HELP spj_total_mxn Total vendido hoy MXN\n"
                f"spj_total_mxn {total:.2f}\n"
                "# HELP spj_stock_bajo Productos stock bajo minimo\n"
                f"spj_stock_bajo {bajo}\n"
                "# HELP spj_uptime_seconds Tiempo de operacion\n"
                f"spj_uptime_seconds {up}\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._json(503, {"error": str(e)})

    def _not_found(self):
        self.send_response(404); self.end_headers()

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


class HealthServerThread(threading.Thread):
    def __init__(self, port: int = 8766):
        super().__init__(daemon=True, name="HealthServer")
        self.port = port
        self._server = None

    def run(self):
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), HealthHandler)
            logger.info("Health server: http://0.0.0.0:%d/health", self.port)
            self._server.serve_forever()
        except Exception as e:
            logger.error("Health server error: %s", e)

    def stop(self):
        if self._server:
            self._server.shutdown()


_instance = None

def start_health_server(port: int = 8766) -> HealthServerThread:
    global _instance
    if _instance and _instance.is_alive():
        return _instance
    _instance = HealthServerThread(port)
    _instance.start()
    return _instance
