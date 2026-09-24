"""Proveedor Mapbox (Geocoding API v6, búsqueda directa).

Se configura desde Configuración → Integraciones → Mapbox: el token es una
credencial del almacén de secretos, y país, idioma, límite y `permanent` salen
de la configuración de la instancia. La versión perdida lo leía de variables de
entorno, que nadie puede cambiar desde la aplicación.

DOS COSAS DE MAPBOX QUE NO SE PUEDEN IGNORAR
---------------------------------------------
* **Geocodificación temporal vs. permanente.** Los resultados de la API por
  omisión son "temporales": sus condiciones no permiten GUARDARLOS. Este ERP
  guarda las coordenadas en proveedores, clientes y pedidos, así que por omisión
  se pide `permanent=true`. Mapbox factura esa modalidad aparte; si la cuenta no
  la tiene, responde 403 y la cadena pasa al respaldo — el motivo queda a la
  vista en la pantalla, no escondido.
* **Parsear el contexto, no sólo la etiqueta.** La versión anterior se quedaba
  con `full_address` y las coordenadas, y la pantalla no podía rellenar calle,
  número, colonia ni código postal. v6 los trae en `properties.context`.
"""

from __future__ import annotations

from backend.application.addresses.address_search import (
    AddressProviderError,
    AddressSource,
    StructuredAddress,
)

BASE_URL = "https://api.mapbox.com/search/geocode/v6/forward"

_ERRORS = {
    401: "token inválido o caducado",
    403: "acceso denegado (revisa el token o la geocodificación permanente)",
    404: "servicio no encontrado",
    422: "consulta rechazada",
    429: "límite de peticiones alcanzado",
}


def _name(context: dict, key: str) -> str:
    entrada = context.get(key) or {}
    return str(entrada.get("name") or "") if isinstance(entrada, dict) else ""


class MapboxAddressProvider:
    code = "MAPBOX"
    display_name = "Mapbox"
    supports_autocomplete = True
    attribution = "© Mapbox © OpenStreetMap"

    def __init__(self, *, token: str, country: str = "mx", language: str = "es",
                 permanent: bool = True, timeout: float = 5.0, http_get=None) -> None:
        token = str(token or "").strip()
        if not token:
            raise AddressProviderError("sin token configurado")
        self._token = token
        self._country = str(country or "mx").lower()
        self._language = str(language or "es")
        self._permanent = bool(permanent)
        self._timeout = float(timeout)
        if http_get is None:
            from backend.infrastructure.maps.http_client import default_http_get
            http_get = default_http_get
        self._http_get = http_get

    def search(self, query: str, *, limit: int) -> list[StructuredAddress]:
        params = {
            "q": query, "access_token": self._token, "country": self._country,
            "language": self._language, "limit": max(1, min(int(limit), 10)),
            "autocomplete": "true", "permanent": "true" if self._permanent else "false",
        }
        try:
            respuesta = self._http_get(BASE_URL, params=params, timeout=self._timeout)
        except Exception as exc:
            raise AddressProviderError("sin conexión con el servicio") from exc
        estado = int(getattr(respuesta, "status_code", 0) or 0)
        if estado in _ERRORS:
            raise AddressProviderError(_ERRORS[estado])
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
    def parse(payload: dict) -> list[StructuredAddress]:
        resultados: list[StructuredAddress] = []
        for feature in (payload or {}).get("features") or []:
            props = feature.get("properties") or {}
            contexto = props.get("context") or {}
            direccion = contexto.get("address") or {}
            coords = props.get("coordinates") or {}
            lat, lon = coords.get("latitude"), coords.get("longitude")
            geometria = feature.get("geometry") or {}
            if (lat is None or lon is None) and geometria.get("type") == "Point":
                lon, lat = (list(geometria.get("coordinates") or []) + [None, None])[:2]

            calle = (direccion.get("street_name") or _name(contexto, "street")
                     or (props.get("name") if props.get("feature_type") == "street" else ""))
            pais = (contexto.get("country") or {}).get("country_code") or "MX"
            try:
                resultados.append(StructuredAddress(
                    street=calle or "",
                    exterior_number=direccion.get("address_number") or "",
                    neighborhood=_name(contexto, "neighborhood") or _name(contexto, "locality"),
                    municipality=_name(contexto, "place") or _name(contexto, "district"),
                    state=_name(contexto, "region"),
                    postal_code=_name(contexto, "postcode"),
                    country_code=pais,
                    latitude=lat, longitude=lon,
                    source=AddressSource.MAPBOX,
                    label=(props.get("full_address") or props.get("place_formatted")
                           or props.get("name") or "")))
            except ValueError:
                # Una coordenada imposible descarta ESA sugerencia, no la búsqueda.
                continue
        return resultados
