# core/logging_setup.py — SPJ POS v10
"""
Logging estructurado con rotacion automatica.
  - logs/spj_pos.log     — log principal (rotacion diaria, 30 dias)
  - logs/errores.log     — solo ERROR y CRITICAL (7 dias)
  - logs/ventas.log      — auditoria de ventas (90 dias)
  - logs/accesos.log     — login/logout (90 dias)
Formato JSON para facilitar analisis con herramientas externas.
"""
from __future__ import annotations
import logging, logging.handlers, os, json
from datetime import datetime


class JsonFormatter(logging.Formatter):
    """Formatea cada log como una linea JSON.

    El logging no debe romper la operación si un caller usa un especificador
    incompatible, por ejemplo ``%d`` con ``None``. En ese caso se conserva el
    mensaje base y los argumentos crudos para auditoría.
    """
    def _safe_message(self, record: logging.LogRecord) -> str:
        try:
            return record.getMessage()
        except Exception as exc:
            try:
                return f"{record.msg} | args={record.args!r} | format_error={exc}"
            except Exception:
                return f"<log message unavailable: {exc}>"

    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts":      datetime.utcnow().isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     self._safe_message(record),
            "module":  record.module,
            "line":    record.lineno,
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


class SafeTextFormatter(logging.Formatter):
    """Text formatter that also survives malformed log format arguments."""
    def format(self, record: logging.LogRecord) -> str:
        try:
            return super().format(record)
        except Exception as exc:
            original_msg = record.msg
            original_args = record.args
            try:
                record.msg = f"{original_msg} | args={original_args!r} | format_error={exc}"
                record.args = ()
                return super().format(record)
            finally:
                record.msg = original_msg
                record.args = original_args


def setup_logging(log_dir: str = "logs",
                  level: str   = "INFO",
                  json_format: bool = True) -> None:
    """
    Configura el sistema de logging global de SPJ POS.
    Llamar una sola vez al inicio de la aplicacion.
    """
    os.makedirs(log_dir, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt_cls  = JsonFormatter if json_format else None
    text_fmt = SafeTextFormatter(
        "%(asctime)s %(levelname)-8s %(name)-30s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")

    def _make_handler(filename: str, level: int,
                      when: str = "midnight", backup: int = 30) -> logging.Handler:
        path = os.path.join(log_dir, filename)
        h    = logging.handlers.TimedRotatingFileHandler(
            path, when=when, backupCount=backup, encoding="utf-8")
        h.setLevel(level)
        h.setFormatter(fmt_cls() if fmt_cls else text_fmt)
        return h

    # Consola — solo WARNING+ para no ensuciar la terminal
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(text_fmt)

    handlers = [
        console,
        _make_handler("spj_pos.log",  logging.DEBUG,   backup=30),
        _make_handler("errores.log",  logging.ERROR,   backup=7),
        _make_handler("ventas.log",   logging.DEBUG,   backup=90),
        _make_handler("accesos.log",  logging.DEBUG,   backup=90),
    ]

    # Filtros especializados
    class VentasFilter(logging.Filter):
        def filter(self, r): return "spj.ventas" in r.name or "spj.sales" in r.name

    class AccesosFilter(logging.Filter):
        def filter(self, r): return "spj.auth" in r.name or "spj.login" in r.name

    handlers[3].addFilter(VentasFilter())
    handlers[4].addFilter(AccesosFilter())

    for h in handlers:
        root.addHandler(h)

    logging.getLogger("spj").info("Logging configurado — dir=%s level=%s", log_dir, level)
