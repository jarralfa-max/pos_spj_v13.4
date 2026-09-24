"""Cliente HTTP compartido por los proveedores de mapas.

Una sola `requests.Session` por proceso: el autocompletado hace muchas
peticiones seguidas al mismo host, y reutilizar la conexión TLS es la diferencia
entre una sugerencia que llega mientras se escribe y una que llega tarde.

Los proveedores reciben `http_get` INYECTADO; éste es sólo el de producción.
Así las pruebas nunca tocan la red.
"""

from __future__ import annotations

import threading

_USER_AGENT = "SPJ-POS-ERP/13.4 (direcciones)"

_session = None
_lock = threading.Lock()


def _get_session():
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                import requests
                from requests.adapters import HTTPAdapter

                sesion = requests.Session()
                sesion.headers.update({"User-Agent": _USER_AGENT,
                                       "Accept": "application/json"})
                sesion.mount("https://", HTTPAdapter(pool_connections=2, pool_maxsize=8,
                                                     max_retries=0))
                _session = sesion
    return _session


def default_http_get(url: str, *, params: dict, headers: dict | None = None,
                     timeout: float = 5.0):
    """Devuelve la respuesta de `requests` tal cual; los proveedores
    interpretan el código de estado. Las excepciones de red se propagan."""
    return _get_session().get(url, params=params, headers=headers or {}, timeout=timeout)
