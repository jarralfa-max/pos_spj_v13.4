"""Caché LRU con caducidad para búsquedas de direcciones.

Recuperada en espíritu de la versión perdida (`core/cache/address_cache.py`,
commit `42f0ed01`): los workers de búsqueda corren en hilos del `QThreadPool`,
así que la caché tiene que ser segura entre hilos. Es de proceso y sobrevive a
cerrar y reabrir un diálogo, que es justo cuando más se repite una búsqueda.

Guarda resultados de sesión, no direcciones: lo que se persiste en cada módulo
es la dirección que el usuario eligió, no esta caché.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict


class AddressSearchCache:
    def __init__(self, *, max_size: int = 200, ttl_seconds: float = 3600.0,
                 clock=time.monotonic) -> None:
        self._max = max(1, int(max_size))
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key):
        with self._lock:
            entrada = self._data.get(key)
            if entrada is None:
                return None
            valor, vence = entrada
            if self._clock() >= vence:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return valor

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = (value, self._clock() + self._ttl)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
