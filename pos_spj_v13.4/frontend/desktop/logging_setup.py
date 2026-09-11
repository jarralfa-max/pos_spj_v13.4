"""Configuración de logging del escritorio.

`core/logging_setup.py` desapareció con la carpeta `core/` y no se recupera del
historial (§18). Esto NO pretende reproducirlo: es una configuración mínima y
explícita, escrita contra lo que la aplicación necesita hoy — consola para
desarrollo y un archivo rotado por día en `logs/`, que es la carpeta que el
proyecto ya usa y donde están los registros existentes.

Es idempotente a propósito: `configure_logging()` puede llamarse más de una vez
(tests, reinicio del shell) sin acabar con la línea duplicada tantas veces como
llamadas, que es lo que pasa cuando se añaden manejadores al logger raíz sin
comprobar los que ya están.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"

#: Marca en los manejadores que instala este módulo, para reconocerlos en una
#: segunda llamada. Comprobar el tipo no bastaría: otra librería puede haber
#: instalado su propio `StreamHandler` en el logger raíz y no es nuestro.
_MARKER = "_spj_desktop_logging"


def _already_configured(root: logging.Logger) -> bool:
    return any(getattr(handler, _MARKER, False) for handler in root.handlers)


def configure_logging(logs_dir: Path, *, level: int = logging.INFO) -> None:
    """Deja el logger raíz escribiendo a consola y a `logs/spj_pos.log`.

    Si la carpeta de logs no se puede crear o abrir (permisos, disco lleno,
    carpeta de sólo lectura), se configura sólo la consola en vez de impedir el
    arranque: quedarse sin archivo de log es un inconveniente, no una razón
    para que la aplicación no abra.
    """
    root = logging.getLogger()
    if _already_configured(root):
        return

    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    setattr(console, _MARKER, True)
    root.addHandler(console)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        archivo = logging.handlers.TimedRotatingFileHandler(
            logs_dir / "spj_pos.log", when="midnight", encoding="utf-8",
        )
        archivo.setFormatter(formatter)
        setattr(archivo, _MARKER, True)
        root.addHandler(archivo)
    except OSError as exc:
        root.warning("No se pudo abrir el archivo de log en %s: %s", logs_dir, exc)
