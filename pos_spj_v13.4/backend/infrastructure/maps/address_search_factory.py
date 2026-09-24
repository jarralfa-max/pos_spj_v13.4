"""Arma el `AddressSearchService` desde Configuración → Integraciones.

Es la única raíz de composición de la búsqueda de direcciones: TODAS las
pantallas la obtienen de aquí, así que configurar Mapbox una vez lo activa en
Clientes, Proveedores, Delivery y Configuración a la vez.

DE DÓNDE SALE CADA COSA
-----------------------
    Integración MAPBOX (categoría LOCATION)
        activa (definición + instancia)   -> se usa o no
        credencial `mapbox_access_token`  -> nombre del secreto; el TOKEN se
                                             lee del almacén de secretos
        config: country, language, limit, permanent
    Integración NOMINATIM (categoría LOCATION)
        activa                            -> se usa o no
        config: country, language, contact_email

El almacén de secretos es `build_default_secret_store()`, el MISMO que usa la
pantalla de Integraciones al guardar la credencial
(`configuracion/shell_registration.py`). Usar otro haría que el token guardado
desde la pantalla no se encontrara nunca.

La migración 264 siembra las dos integraciones. En una base donde no corrió,
Mapbox no existe (no hay de dónde sacar el token) y Nominatim se usa con valores
por omisión: el respaldo lo pidió el usuario y no requiere nada configurado.

NUNCA LANZA. Cualquier fallo al leer la configuración deja fuera ESE proveedor
y se registra; lo peor que puede pasar es acabar en captura manual, que siempre
funciona. Una pantalla de alta de cliente no puede dejar de abrir porque el
almacén de secretos no respondió.
"""

from __future__ import annotations

import logging

from backend.application.addresses.address_search import (
    DEFAULT_LIMIT,
    AddressSearchService,
)
from backend.infrastructure.maps.address_cache import AddressSearchCache

logger = logging.getLogger("spj.addresses.factory")

MAPBOX_CODE = "MAPBOX"
NOMINATIM_CODE = "NOMINATIM"
MAPBOX_CREDENTIAL = "mapbox_access_token"

#: Una caché por proceso: sobrevive a cerrar y reabrir diálogos.
_SHARED_CACHE = AddressSearchCache(max_size=200, ttl_seconds=3600)


def _truthy(valor, defecto: bool) -> bool:
    if valor is None or valor == "":
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _integration(connection, code: str):
    """`(definición, instancia)` o `(None, None)`. La instancia es la primera
    de esa definición, igual que `mercadopago_credential_resolver`."""
    from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
        SqliteIntegrationDefinitionRepository,
    )
    from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
        SqliteIntegrationInstanceRepository,
    )
    # Sin el esquema de Integraciones (la 219 no corrió, o una base mínima) no
    # hay configuración que leer: se responde "no existe" en vez de lanzar. Si
    # lanzara, se perdería también el respaldo Nominatim, que no requiere nada
    # configurado y es justo el que tiene que seguir funcionando.
    fila = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='integration_definitions'"
    ).fetchone()
    if fila is None:
        return None, None
    definicion = SqliteIntegrationDefinitionRepository(connection).get_by_code(code)
    if definicion is None:
        return None, None
    instancias = SqliteIntegrationInstanceRepository(connection).list_by_definition(definicion.id)
    return definicion, (instancias[0] if instancias else None)


def _mapbox(connection, secret_store, http_get):
    definicion, instancia = _integration(connection, MAPBOX_CODE)
    if definicion is None or instancia is None:
        return None
    if not (definicion.active and instancia.active):
        return None
    secreto = (instancia.credential_references or {}).get(MAPBOX_CREDENTIAL)
    if not secreto:
        return None
    if secret_store is None:
        from backend.security.secrets.default_secret_store import build_default_secret_store
        secret_store = build_default_secret_store()
    token = str(secret_store.get_secret(secreto) or "").strip()
    if not token:
        logger.warning("Mapbox está activo pero su credencial %r no tiene valor", secreto)
        return None
    config = dict(instancia.config or {})
    from backend.infrastructure.maps.mapbox_address_provider import MapboxAddressProvider
    return MapboxAddressProvider(
        token=token, country=config.get("country") or "mx",
        language=config.get("language") or "es",
        permanent=_truthy(config.get("permanent"), True), http_get=http_get)


def _nominatim(connection, http_get):
    definicion, instancia = _integration(connection, NOMINATIM_CODE)
    config: dict = {}
    if definicion is not None:
        if not definicion.active or (instancia is not None and not instancia.active):
            return None
        config = dict(getattr(instancia, "config", None) or {})
    from backend.infrastructure.maps.nominatim_address_provider import (
        NominatimAddressProvider,
    )
    return NominatimAddressProvider(
        country=config.get("country") or "mx", language=config.get("language") or "es",
        contact_email=config.get("contact_email") or "", http_get=http_get)


def _limit(connection) -> int:
    for codigo in (MAPBOX_CODE, NOMINATIM_CODE):
        try:
            _definicion, instancia = _integration(connection, codigo)
        except Exception:
            continue
        valor = (getattr(instancia, "config", None) or {}).get("limit") if instancia else None
        try:
            if valor:
                return int(valor)
        except (TypeError, ValueError):
            continue
    return DEFAULT_LIMIT


def build_address_search_service(connection, *, secret_store=None, http_get=None,
                                 cache=None) -> AddressSearchService:
    """El servicio con la cadena Mapbox → Nominatim ya armada. Sin proveedores
    utilizables devuelve un servicio vacío, que responde `NOT_CONFIGURED`."""
    proveedores = []
    for nombre, construir in (
            ("Mapbox", lambda: _mapbox(connection, secret_store, http_get)),
            ("Nominatim", lambda: _nominatim(connection, http_get))):
        try:
            proveedor = construir()
        except Exception:
            logger.exception("No se pudo preparar el proveedor de direcciones %s", nombre)
            continue
        if proveedor is not None:
            proveedores.append(proveedor)
    try:
        limite = _limit(connection)
    except Exception:
        limite = DEFAULT_LIMIT
    return AddressSearchService(
        proveedores, cache=cache if cache is not None else _SHARED_CACHE, limit=limite)
