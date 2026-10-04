"""Guardas compartidas por los casos de uso de listas y de precios.

Existen para que la captura individual, la captura en lote, las escalas por
volumen y el ciclo de vida apliquen EXACTAMENTE las mismas reglas y den el mismo
mensaje. Antes cada caso de uso redactaba la suya: el lote decía "duplícala", el
individual "crea una nueva", la escala por volumen no miraba el estado de la
lista en absoluto, y un estado guardado que no fuera canónico reventaba como
"error inesperado".

Cada guarda devuelve un `PricingResult` fallido (o `None` si pasa) y nunca
lanza para los casos esperados.
"""

from __future__ import annotations

from datetime import date

from backend.application.pricing.result import PricingResult
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.enums import (
    EDITABLE_LIST_STATES,
    PRICE_LIST_STATUS_LABELS,
    PriceListStatus,
)
from backend.domain.pricing.exceptions import UnknownPriceListStatusError
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)


def status_label(status: PriceListStatus) -> str:
    return PRICE_LIST_STATUS_LABELS.get(status, status.value)


def load_list(repo: PricingRepository, price_list_id: str, *, operation_id: str
              ) -> tuple[PriceList | None, PricingResult | None]:
    """La lista, o el fallo que explica por qué no se puede usar."""
    try:
        price_list = repo.get_list(price_list_id)
    except UnknownPriceListStatusError as exc:
        return None, PricingResult.fail(
            str(exc), "UNKNOWN_STATUS", operation_id=operation_id,
            raw_status=exc.raw_status, list_code=exc.code)
    if price_list is None:
        return None, PricingResult.fail("La lista de precios no existe", "NOT_FOUND",
                                        operation_id=operation_id)
    return price_list, None


def read_only_failure(price_list: PriceList, *, operation_id: str) -> PricingResult | None:
    """`None` si la lista recibe precios; si no, el fallo con la salida.

    La salida es SIEMPRE duplicar: el dominio no tiene versionado de listas, y
    duplicar crea un borrador con los mismos precios que sí se puede capturar,
    enviar a revisión, aprobar y activar (al activarse, una lista base
    reemplaza a la anterior).
    """
    if price_list.is_editable:
        return None
    estado = status_label(price_list.status)
    if price_list.status is PriceListStatus.INACTIVE:
        motivo = "está Inactiva: sus precios son historia y no se modifican"
    else:
        motivo = f"está {estado} y es de solo lectura"
    return PricingResult.fail(
        f"La lista «{price_list.code}» {motivo}. Para cambiar sus precios, "
        "duplícala en «Listas de precio»: la copia nace en Borrador con los "
        "mismos precios, ahí los editas y la envías a revisión.",
        "IMMUTABLE_LIST", operation_id=operation_id,
        list_status=price_list.status.value, list_code=price_list.code,
        recovery="DUPLICATE")


def missing_prices_failure(repo: PricingRepository, price_list: PriceList, *,
                           stored_status: PriceListStatus, operation_id: str,
                           action: str, on_date: str | None = None
                           ) -> PricingResult | None:
    """`None` si la lista tiene al menos un precio que rige hoy o después.

    Regla: AL MENOS UN precio no vencido. El dominio no define cobertura por
    categoría ni por producto y no se inventa aquí; lo que sí es seguro es que
    una lista vacía —o con todos sus precios vencidos— que se activa no le da
    al POS ningún precio, y si es base, además retira a la que sí los tenía.

    `action` es "aprobar" o "activar" y `stored_status` el estado GUARDADO
    (la entidad ya transicionó en memoria): el remedio depende de él. Una lista
    en revisión todavía acepta precios; una APROBADA ya no, así que la única
    salida es duplicarla.
    """
    dia = (on_date or date.today().isoformat())[:10]
    total, vigentes = repo.price_counts(price_list.id, on_date=dia)
    if vigentes > 0:
        return None
    if total == 0:
        falta = "no tiene precios capturados"
    else:
        falta = f"sus {total} precio(s) ya vencieron"
    if stored_status in EDITABLE_LIST_STATES:
        remedio = ("Captura al menos un precio en «Precios por producto» "
                   "(la lista sigue aceptando precios mientras está en "
                   f"{status_label(stored_status)}) y vuelve a intentarlo.")
    else:
        remedio = ("Como ya no acepta precios, duplícala en «Listas de precio», "
                   "captura los precios en la copia y llévala por revisión, "
                   "aprobación y activación.")
    return PricingResult.fail(
        f"No se puede {action} la lista «{price_list.code}»: {falta}. {remedio}",
        "EMPTY_LIST", operation_id=operation_id, list_status=stored_status.value,
        list_code=price_list.code, price_count=total, usable_price_count=vigentes)
