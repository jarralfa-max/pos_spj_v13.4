"""Búsqueda y captura de direcciones — UN estándar para todos los módulos.

QUÉ HABÍA ANTES, MEDIDO (2026-09-17)
-------------------------------------
* `AddressInput` existía y **ninguna pantalla lo construía**. Su proveedor por
  omisión era `lambda _query: []`, disparaba en cada tecla desde la primera, y
  `value()` devolvía sólo la etiqueta: tiraba la latitud y la longitud.
* La geocodificación con Mapbox **se construyó y se perdió**: el commit
  `42f0ed01` tenía proveedor Mapbox v6, respaldo Nominatim, caché LRU+TTL,
  workers asíncronos y mínimo de 5 caracteres. Vivía en `core/` y se fue con el
  legacy; sólo sobrevivió un test de arquitectura que apuntaba a tres archivos
  borrados. Esa versión, además, devolvía `[]` ante cualquier error —la misma
  confusión entre "falló" y "no hay coincidencias" que ya se corrigió en las
  búsquedas de productos y clientes—, guardaba sólo etiqueta y coordenadas, y
  leía el token de variables de entorno.
* Cada módulo capturaba la dirección a su manera: Delivery en seis campos,
  Proveedores en cinco, Configuración en uno, Clientes en ninguno (su caso de
  uso de alta de dirección no tenía llamador).

QUÉ ES ESTO
-----------
El VALOR (`StructuredAddress`), el PUERTO de proveedor y el SERVICIO con la
cadena de respaldo. Sin I/O: los proveedores concretos viven en
`backend/infrastructure/maps/`, y la fábrica que lee su configuración desde
Configuración → Integraciones también.

LA CADENA DE RESPALDO — decisión del usuario: Mapbox → Nominatim → manual
---------------------------------------------------------------------------
Se pasa al siguiente proveedor cuando el anterior **FALLA** (sin token, sin red,
401, 429, 5xx), no cuando responde "cero coincidencias". Cero coincidencias es
una respuesta válida: repetirla contra otro servicio duplica el tráfico y, en el
caso de Nominatim, gasta un cupo que su política limita a una petición por
segundo.

NOMINATIM NO ADMITE AUTOCOMPLETADO — por eso existe `NEEDS_EXPLICIT_SEARCH`
---------------------------------------------------------------------------
La política de uso de Nominatim (OSM Foundation) prohíbe implementar
autocompletado del lado del cliente contra su API. Cada proveedor declara
`supports_autocomplete`; cuando la búsqueda viene del teclado
(`interactive=True`) y el siguiente proveedor disponible no lo admite, el
servicio NO lo llama: devuelve `NEEDS_EXPLICIT_SEARCH` y la pantalla pide pulsar
Enter. Con Enter la búsqueda ya no es autocompletado sino una consulta
explícita, que la política sí permite. El respaldo existe; sólo cambia el gesto.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Protocol, Sequence

logger = logging.getLogger("spj.addresses.search")

#: Mínimo de caracteres antes de consultar a un proveedor. Decisión del usuario,
#: y la misma cifra que tenía la versión perdida. Es la ÚNICA fuente: el
#: componente de pantalla la importa de aquí en lugar de repetirla.
MIN_QUERY_CHARS = 5

#: Sugerencias por consulta. Configurable por proveedor desde Integraciones
#: (`config.limit`); éste es sólo el valor cuando nadie lo fija.
DEFAULT_LIMIT = 5


class AddressSource(str, Enum):
    """De dónde salió la dirección. `MANUAL` es un estado legítimo, no un error:
    la captura manual siempre debe poder completar la operación."""

    MAPBOX = "MAPBOX"
    NOMINATIM = "NOMINATIM"
    MANUAL = "MANUAL"


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _coordinate(value, *, limit: float, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        numero = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} inválida: {value!r}") from exc
    if not -limit <= numero <= limit:
        raise ValueError(f"{name} fuera de rango: {numero}")
    return numero


@dataclass(frozen=True)
class StructuredAddress:
    """La dirección, igual en todos los módulos.

    El conjunto de campos es el que ya pedía `AddCustomerAddressUseCase` —el más
    completo del repositorio—; cada módulo guarda el subconjunto que su esquema
    admite. Configuración, que sólo guarda una línea, usa `one_line()`.
    """

    street: str = ""
    exterior_number: str = ""
    interior_number: str = ""
    neighborhood: str = ""
    municipality: str = ""
    state: str = ""
    postal_code: str = ""
    country_code: str = "MX"
    references: str = ""
    latitude: float | None = None
    longitude: float | None = None
    source: AddressSource = AddressSource.MANUAL
    #: Texto con el que el proveedor presentó la sugerencia. No se guarda como
    #: dirección: sólo sirve para enseñarla en la lista.
    label: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        for nombre in ("street", "exterior_number", "interior_number", "neighborhood",
                       "municipality", "state", "postal_code", "references", "label"):
            object.__setattr__(self, nombre, _clean(getattr(self, nombre)))
        object.__setattr__(self, "country_code",
                           (_clean(self.country_code) or "MX").upper())
        lat = _coordinate(self.latitude, limit=90.0, name="Latitud")
        lon = _coordinate(self.longitude, limit=180.0, name="Longitud")
        if (lat is None) != (lon is None):
            # Media coordenada no ubica nada, y guardarla haría creer que sí.
            lat = lon = None
        object.__setattr__(self, "latitude", lat)
        object.__setattr__(self, "longitude", lon)
        object.__setattr__(self, "source", AddressSource(self.source))

    # ── lectura ──────────────────────────────────────────────────────────
    @property
    def is_geocoded(self) -> bool:
        """Coordenadas de un proveedor. Una dirección manual nunca lo está,
        aunque alguien le haya dejado coordenadas viejas."""
        return (self.source is not AddressSource.MANUAL
                and self.latitude is not None and self.longitude is not None)

    @property
    def is_empty(self) -> bool:
        return not any((self.street, self.exterior_number, self.neighborhood,
                        self.municipality, self.state, self.postal_code))

    def street_line(self) -> str:
        """Calle y números en una línea: "Av. Juárez 120 Int. 4"."""
        partes = [self.street, self.exterior_number]
        linea = " ".join(p for p in partes if p)
        if self.interior_number:
            linea = f"{linea} Int. {self.interior_number}".strip()
        return linea

    def one_line(self) -> str:
        """La dirección completa en una línea, para los módulos que guardan
        un solo campo de texto."""
        partes = [self.street_line()]
        if self.neighborhood:
            partes.append(f"Col. {self.neighborhood}")
        partes.extend(p for p in (self.municipality, self.state) if p)
        if self.postal_code:
            partes.append(f"C.P. {self.postal_code}")
        return ", ".join(p for p in partes if p)

    # ── cambios ──────────────────────────────────────────────────────────
    def as_manual(self) -> "StructuredAddress":
        """Lo que queda cuando el usuario corrige a mano lo que ubica la
        dirección: los datos se conservan, las coordenadas NO — ya no
        corresponden a lo escrito."""
        return replace(self, source=AddressSource.MANUAL, latitude=None, longitude=None)

    def with_changes(self, **cambios) -> "StructuredAddress":
        return replace(self, **cambios)

    def to_dict(self) -> dict:
        datos = asdict(self)
        datos["source"] = self.source.value
        datos.pop("label", None)
        return datos

    @classmethod
    def from_one_line(cls, text: str) -> "StructuredAddress":
        """Para cargar lo que un módulo guardó como una sola línea. No se
        intenta partirla: una heurística que adivine la colonia dentro de un
        texto libre acierta a veces y falla en silencio las demás."""
        return cls(street=text or "")

    @classmethod
    def from_mapping(cls, datos: dict | None) -> "StructuredAddress":
        datos = dict(datos or {})
        conocidos = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in datos.items() if k in conocidos})


class AddressProviderError(Exception):
    """El proveedor NO pudo responder (sin token, sin red, rechazo, cupo).

    Distinto a propósito de "respondió sin coincidencias", que es `[]`. Mezclar
    los dos fue el defecto de la versión anterior: un token caducado se veía en
    pantalla exactamente igual que una calle que no existe.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AddressSearchProvider(Protocol):
    code: str
    display_name: str
    #: ¿Admite consultas por cada tecla? Nominatim NO (política de uso).
    supports_autocomplete: bool
    #: Atribución que el proveedor exige mostrar junto a sus resultados.
    attribution: str

    def search(self, query: str, *, limit: int) -> list[StructuredAddress]:
        """Lanza `AddressProviderError` si no pudo responder; `[]` si respondió
        sin coincidencias."""
        ...


class AddressSearchStatus(str, Enum):
    OK = "OK"
    NO_RESULTS = "NO_RESULTS"
    TOO_SHORT = "TOO_SHORT"
    #: El proveedor disponible no admite autocompletado: hay que pulsar Enter.
    NEEDS_EXPLICIT_SEARCH = "NEEDS_EXPLICIT_SEARCH"
    #: Ningún proveedor respondió.
    UNAVAILABLE = "UNAVAILABLE"
    #: No hay ningún proveedor configurado ni activo.
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class AddressSearchResult:
    status: AddressSearchStatus
    suggestions: tuple[StructuredAddress, ...] = ()
    provider_code: str | None = None
    #: Mensaje para quien opera. Vacío cuando todo salió bien.
    message: str = ""
    attribution: str = ""
    #: Qué falló antes de llegar aquí, por proveedor. Para el registro y para
    #: que la pantalla pueda explicar por qué los resultados no son de Mapbox.
    failures: tuple[str, ...] = ()


class _AddressCache(Protocol):
    def get(self, key): ...

    def put(self, key, value) -> None: ...


class _NoCache:
    def get(self, key):
        return None

    def put(self, key, value) -> None:
        return None


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "")).strip()


class AddressSearchService:
    """La cadena de respaldo. Sin estado propio salvo la caché inyectada, así
    que puede llamarse desde varios hilos a la vez."""

    def __init__(self, providers: Sequence[AddressSearchProvider] = (), *,
                 cache: _AddressCache | None = None, limit: int = DEFAULT_LIMIT) -> None:
        self._providers = tuple(providers)
        # `is not None` y NO `or`: una caché vacía define `__len__` == 0 y es
        # FALSA, así que `cache or _NoCache()` la descartaba siempre y la caché
        # compartida no se usaba nunca. Lo atrapó `test_results_are_cached`.
        self._cache = cache if cache is not None else _NoCache()
        self._limit = max(1, min(int(limit), 10))

    @property
    def providers(self) -> tuple[AddressSearchProvider, ...]:
        return self._providers

    def autocomplete_available(self) -> bool:
        """¿Se puede buscar mientras se escribe? Sólo si el PRIMER proveedor lo
        admite; si no, la pantalla pide Enter desde el principio."""
        return bool(self._providers) and bool(self._providers[0].supports_autocomplete)

    def search(self, query: str, *, interactive: bool) -> AddressSearchResult:
        texto = normalize_query(query)
        if len(texto) < MIN_QUERY_CHARS:
            return AddressSearchResult(
                AddressSearchStatus.TOO_SHORT,
                message=f"Escribe al menos {MIN_QUERY_CHARS} caracteres para buscar.")
        if not self._providers:
            return AddressSearchResult(
                AddressSearchStatus.NOT_CONFIGURED,
                message="La búsqueda de direcciones no está configurada "
                        "(Configuración → Integraciones). Captura la dirección a mano.")

        fallos: list[str] = []
        for proveedor in self._providers:
            if interactive and not proveedor.supports_autocomplete:
                previo = f"{fallos[-1]}. " if fallos else ""
                return AddressSearchResult(
                    AddressSearchStatus.NEEDS_EXPLICIT_SEARCH,
                    provider_code=proveedor.code, failures=tuple(fallos),
                    message=f"{previo}Presiona Enter para buscar con "
                            f"{proveedor.display_name}.")
            clave = (proveedor.code, texto.casefold(), self._limit)
            guardado = self._cache.get(clave)
            if guardado is not None:
                return self._result(tuple(guardado), proveedor, fallos)
            try:
                encontrados = tuple(proveedor.search(texto, limit=self._limit))
            except AddressProviderError as exc:
                fallos.append(f"{proveedor.display_name}: {exc.reason}")
                logger.warning("Búsqueda de direcciones: %s falló (%s)",
                               proveedor.code, exc.reason)
                continue
            except Exception:
                # Un proveedor que revienta de forma inesperada no puede tumbar la
                # cadena: se trata como no disponible y se registra completo.
                fallos.append(f"{proveedor.display_name}: error inesperado")
                logger.exception("Búsqueda de direcciones: %s reventó", proveedor.code)
                continue
            self._cache.put(clave, encontrados)
            return self._result(encontrados, proveedor, fallos)

        return AddressSearchResult(
            AddressSearchStatus.UNAVAILABLE, failures=tuple(fallos),
            message="No se pudo buscar la dirección ("
                    + "; ".join(fallos) + "). Captúrala manualmente.")

    @staticmethod
    def _result(encontrados: tuple[StructuredAddress, ...], proveedor,
                fallos: list[str]) -> AddressSearchResult:
        aviso = ("; ".join(fallos) + f". Resultados de {proveedor.display_name}."
                 if fallos else "")
        if encontrados:
            return AddressSearchResult(
                AddressSearchStatus.OK, suggestions=encontrados,
                provider_code=proveedor.code, message=aviso,
                attribution=proveedor.attribution, failures=tuple(fallos))
        return AddressSearchResult(
            AddressSearchStatus.NO_RESULTS, provider_code=proveedor.code,
            attribution=proveedor.attribution, failures=tuple(fallos),
            message=(aviso + " " if aviso else "")
            + "Sin coincidencias; revisa el texto o captura la dirección a mano.")
