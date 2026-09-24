"""Proveedor de respaldo: Nominatim (OpenStreetMap). No requiere token.

Decisión del usuario: cuando Mapbox no está configurado o falla, se usa éste
antes de caer a la captura manual.

LA POLÍTICA DE USO DE NOMINATIM MANDA SOBRE LA COMODIDAD
---------------------------------------------------------
La OSM Foundation fija condiciones para su servidor público, y romperlas acaba
en el bloqueo de la IP de la tienda:

* **No se permite autocompletado del lado del cliente.** Por eso
  `supports_autocomplete = False`: el servicio de búsqueda nunca lo llama
  mientras se escribe, sólo cuando se pulsa Enter.
* **Una petición por segundo como máximo.** Se hace cumplir aquí con un candado
  de proceso: si llega otra antes de tiempo, el hilo del worker espera (nunca el
  de la interfaz — la búsqueda siempre corre fuera de él).
* **Identificarse.** `User-Agent` propio y, si se configura, `email` de
  contacto (Configuración → Integraciones → OpenStreetMap, `contact_email`).
* **Atribución visible**: `© OpenStreetMap`, que la pantalla muestra junto a los
  resultados.
"""

from __future__ import annotations

import threading
import time

from backend.application.addresses.address_search import (
    AddressProviderError,
    AddressSource,
    StructuredAddress,
)

BASE_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_SECONDS = 1.0

_rate_lock = threading.Lock()
_last_request = [0.0]


def _first(datos: dict, *claves: str) -> str:
    for clave in claves:
        valor = datos.get(clave)
        if valor:
            return str(valor)
    return ""


class NominatimAddressProvider:
    code = "NOMINATIM"
    display_name = "OpenStreetMap"
    supports_autocomplete = False
    attribution = "© OpenStreetMap"

    def __init__(self, *, country: str = "mx", language: str = "es",
                 contact_email: str = "", timeout: float = 6.0, http_get=None,
                 clock=time.monotonic, sleep=time.sleep) -> None:
        self._country = str(country or "mx").lower()
        self._language = str(language or "es")
        self._email = str(contact_email or "").strip()
        self._timeout = float(timeout)
        if http_get is None:
            from backend.infrastructure.maps.http_client import default_http_get
            http_get = default_http_get
        self._http_get = http_get
        self._clock = clock
        self._sleep = sleep

    def _respect_rate_limit(self) -> None:
        with _rate_lock:
            espera = MIN_INTERVAL_SECONDS - (self._clock() - _last_request[0])
            if espera > 0:
                self._sleep(espera)
            _last_request[0] = self._clock()

    def search(self, query: str, *, limit: int) -> list[StructuredAddress]:
        params = {"q": query, "format": "jsonv2", "addressdetails": 1,
                  "countrycodes": self._country, "limit": max(1, min(int(limit), 10)),
                  "accept-language": self._language}
        if self._email:
            params["email"] = self._email
        self._respect_rate_limit()
        try:
            respuesta = self._http_get(BASE_URL, params=params, timeout=self._timeout)
        except Exception as exc:
            raise AddressProviderError("sin conexión con el servicio") from exc
        estado = int(getattr(respuesta, "status_code", 0) or 0)
        if estado in (403, 429):
            raise AddressProviderError("el servicio limitó las consultas de esta tienda")
        if estado >= 500 or estado == 0:
            raise AddressProviderError("servicio no disponible")
        if estado >= 400:
            raise AddressProviderError(f"respuesta inesperada ({estado})")
        try:
            cuerpo = respuesta.json()
        except Exception as exc:
            raise AddressProviderError("respuesta ilegible") from exc
        return self.parse(cuerpo)

    @staticmethod
    def parse(payload) -> list[StructuredAddress]:
        resultados: list[StructuredAddress] = []
        for lugar in payload or []:
            direccion = lugar.get("address") or {}
            try:
                resultados.append(StructuredAddress(
                    street=_first(direccion, "road", "pedestrian", "street"),
                    exterior_number=_first(direccion, "house_number"),
                    neighborhood=_first(direccion, "neighbourhood", "suburb", "quarter",
                                        "residential"),
                    # `borough` PRIMERO: en la Ciudad de México la alcaldía
                    # (Cuauhtémoc, Coyoacán…) viene ahí y `city` es "Ciudad de
                    # México", que es el estado. Visto en una consulta real, no
                    # supuesto. En el resto del país no aparece y manda city/
                    # town/village/county.
                    municipality=_first(direccion, "borough", "city", "town", "village",
                                        "municipality", "county"),
                    state=_first(direccion, "state"),
                    postal_code=_first(direccion, "postcode"),
                    country_code=_first(direccion, "country_code") or "MX",
                    latitude=lugar.get("lat"), longitude=lugar.get("lon"),
                    source=AddressSource.NOMINATIM,
                    label=str(lugar.get("display_name") or "")))
            except ValueError:
                continue
        return resultados
