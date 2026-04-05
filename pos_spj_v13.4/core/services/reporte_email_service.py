
# core/services/reporte_email_service.py — SPJ POS v10
"""Envio programado de reportes por email (SMTP)."""
from __future__ import annotations
import logging, smtplib, threading
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from core.db.connection import get_connection
logger = logging.getLogger("spj.email")

class ReporteEmailService:
    def __init__(self, conn=None):
        self.conn = conn or get_connection(); self._init_tables()
    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS email_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                smtp_host TEXT, smtp_port INTEGER DEFAULT 587,
                smtp_user TEXT, smtp_pass TEXT,
                remitente TEXT, destinatarios TEXT,
                activo INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS email_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,  -- diario|semanal|mensual
                hora TEXT DEFAULT '08:00', activo INTEGER DEFAULT 1,
                ultimo_envio DATE
            );
        """)
        for tipo in ("diario","semanal","mensual"):
            try:
                self.conn.execute("INSERT OR IGNORE INTO email_schedule(tipo) VALUES(?)", (tipo,))
            except Exception: pass
        try: self.conn.commit()
        except Exception: pass

    def _get_cfg(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM email_config WHERE id=1 AND activo=1").fetchone()
        return dict(row) if row else None

    def _build_reporte_diario(self) -> str:
        hoy = date.today().isoformat()
        def _q(sql, *p): 
            try: return self.conn.execute(sql,p).fetchone()[0] or 0
            except Exception: return 0
        ventas   = _q("SELECT COUNT(*) FROM ventas WHERE DATE(fecha)=? AND estado='completada'", hoy)
        total    = _q("SELECT COALESCE(SUM(total),0) FROM ventas WHERE DATE(fecha)=? AND estado='completada'", hoy)
        devs     = _q("SELECT COUNT(*) FROM devoluciones WHERE DATE(fecha)=?", hoy)
        lotes    = _q("SELECT COUNT(*) FROM lotes WHERE DATE(fecha_caducidad)<=? AND estado='activo'", hoy)
        stock_bajo = _q("SELECT COUNT(*) FROM productos WHERE existencia<=stock_minimo AND activo=1")
        return f"""<html><body style='font-family:Arial;'>
<h2 style='color:#0F4C81;'>📊 Reporte Diario SPJ POS — {hoy}</h2>
<table style='border-collapse:collapse;width:400px;'>
<tr style='background:#0F4C81;color:white;'><th style='padding:8px;'>Métrica</th><th>Valor</th></tr>
<tr><td style='padding:8px;border:1px solid #ddd;'>Ventas del día</td><td style='border:1px solid #ddd;'>{ventas}</td></tr>
<tr style='background:#f5f5f5;'><td style='padding:8px;border:1px solid #ddd;'>Total vendido</td><td style='border:1px solid #ddd;'>${float(total):,.2f}</td></tr>
<tr><td style='padding:8px;border:1px solid #ddd;'>Devoluciones</td><td style='border:1px solid #ddd;'>{devs}</td></tr>
<tr style='background:#f5f5f5;'><td style='padding:8px;border:1px solid #ddd;'>Lotes por vencer</td><td style='border:1px solid #ddd;color:{"red" if lotes else "green"};'>{lotes}</td></tr>
<tr><td style='padding:8px;border:1px solid #ddd;'>Productos stock bajo</td><td style='border:1px solid #ddd;color:{"red" if stock_bajo else "green"};'>{stock_bajo}</td></tr>
</table>
<p style='color:#666;font-size:12px;'>Generado automáticamente por SPJ POS v10</p>
</body></html>"""

    def enviar_reporte_diario(self) -> bool:
        cfg = self._get_cfg()
        if not cfg: logger.info("Email no configurado"); return False
        html = self._build_reporte_diario()
        return self._enviar(
            cfg, f"Reporte Diario SPJ — {date.today().isoformat()}", html)

    def _enviar(self, cfg: dict, asunto: str, html: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = asunto
            msg["From"]    = cfg["remitente"] or cfg["smtp_user"]
            msg["To"]      = cfg["destinatarios"]
            msg.attach(MIMEText(html, "html", "utf-8"))
            with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"])) as s:
                s.starttls()
                s.login(cfg["smtp_user"], cfg["smtp_pass"])
                s.sendmail(msg["From"], msg["To"].split(","), msg.as_string())
            self.conn.execute(
                "UPDATE email_schedule SET ultimo_envio=date('now') WHERE tipo='diario'")
            try: self.conn.commit()
            except Exception: pass
            logger.info("Reporte enviado a: %s", cfg["destinatarios"])
            return True
        except Exception as e:
            logger.error("Error enviando reporte: %s", e); return False

    def start_scheduler(self):
        def _loop():
            import time
            while True:
                time.sleep(3600)
                try:
                    now = datetime.now()
                    cfg_sch = self.conn.execute(
                        "SELECT * FROM email_schedule WHERE tipo='diario' AND activo=1").fetchone()
                    if cfg_sch:
                        hora = str(cfg_sch["hora"] or "08:00")
                        h, m = map(int, hora.split(":"))
                        if now.hour == h and now.minute < 60 and str(cfg_sch["ultimo_envio"] or "") != date.today().isoformat():
                            self.enviar_reporte_diario()
                except Exception as e: logger.debug("email scheduler: %s", e)
        t = threading.Thread(target=_loop, daemon=True, name="EmailScheduler")
        t.start()
        return t
