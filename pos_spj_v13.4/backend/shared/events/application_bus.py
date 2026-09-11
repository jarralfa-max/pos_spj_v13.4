"""Bus de eventos de la aplicación, con nombres de evento en texto.

Reemplaza `core/events/event_bus.py`, borrado. El contrato no se inventó: lo
fijan sus tres consumidores vivos —los despachadores de bandeja de salida de
Compras, Reparto e Inventario— y el cableado de Compras, que ya llaman
`subscribe(nombre, handler, priority=, label=)` y
`publish(nombre, payload, async_=False)`.

POR QUÉ NO SE REUTILIZA `InMemoryEventBus`
-------------------------------------------
El bus tipado de este mismo paquete trabaja con `EventName` y `DomainEvent`:
un enum compartido y un objeto de evento. Cada contexto acotado, en cambio,
define SU PROPIO vocabulario en texto (`ProcurementEvents`, `OrderEvents`,
`InventoryEvents`…), y ninguno de esos nombres está en `EventName`.

Meterlos todos en ese enum acoplaría el vocabulario compartido a cada contexto
—justo lo que los contextos acotados evitan— y convertir cada carga en un
`DomainEvent` tipado obligaría a reescribir los tres despachadores y su formato
de bandeja de salida. Conviven a propósito: el tipado para eventos de dominio
compartidos, éste para la integración entre contextos.

PRIORIDADES — la tabla la fija CLAUDE.md, no este archivo:

    100  sincronización inmediata (inventario, ventas)
     80  operaciones críticas de negocio
     50  contabilidad / ledger
     30  auditoría
     10  notificaciones secundarias
      5  analítica / BI

Mayor primero. Importa de verdad: si la analítica corriera antes que el
ledger, informaría sobre un asiento que todavía no existe.

UN MANEJADOR QUE FALLA NO TUMBA A LOS DEMÁS. Con `strict=False` —lo que usan
los despachadores— el error se registra y el resto sigue: que la notificación
de una venta falle no puede impedir que su asiento contable se escriba. Con
`strict=True` se propaga, para quien necesite que el fallo aborte.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("spj.events.bus")

#: Prioridad por omisión: "operación crítica de negocio", la franja a la que
#: pertenece la mayoría de las integraciones entre contextos.
DEFAULT_PRIORITY = 80


@dataclass(order=True)
class _Subscription:
    # `order=True` sobre estos dos campos: se ordena por prioridad descendente
    # (de ahí el negativo) y, a igualdad, por orden de suscripción, para que el
    # despacho sea determinista y no dependa del orden de importación.
    _sort_key: tuple = field(init=False, repr=False)
    priority: int
    sequence: int
    handler: Callable[[dict], Any] = field(compare=False)
    label: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        self._sort_key = (-self.priority, self.sequence)


class ApplicationEventBus:
    def __init__(self) -> None:
        self._subscriptions: dict[str, list[_Subscription]] = {}
        self._sequence = 0
        # Las suscripciones se registran al arrancar y las publicaciones pueden
        # llegar desde hilos de trabajo (sincronización, temporizadores).
        self._lock = threading.RLock()

    def subscribe(
        self, event_name: str, handler: Callable[[dict], Any], *,
        priority: int = DEFAULT_PRIORITY, label: str = "",
    ) -> None:
        with self._lock:
            self._sequence += 1
            self._subscriptions.setdefault(str(event_name), []).append(
                _Subscription(priority=priority, sequence=self._sequence,
                              handler=handler, label=label or getattr(handler, "__name__", "")))
            self._subscriptions[str(event_name)].sort()

    def publish(
        self, event_name: str, payload: dict | None = None, *,
        async_: bool = False, strict: bool = False,
    ) -> int:
        """Entrega el evento a sus suscriptores. Devuelve cuántos lo atendieron.

        `async_` se acepta porque los despachadores lo pasan explícitamente,
        pero la entrega es SIEMPRE síncrona: los tres publican dentro de la
        transacción de la operación que los generó, y entregar en otro hilo
        rompería esa atomicidad sin avisar. Se ignora en vez de fingir que se
        respeta.
        """
        del async_
        with self._lock:
            suscriptores = list(self._subscriptions.get(str(event_name), ()))
        if not suscriptores:
            return 0

        datos = dict(payload or {})
        atendidos = 0
        for suscripcion in suscriptores:
            try:
                suscripcion.handler(datos)
                atendidos += 1
            except Exception:
                if strict:
                    raise
                logger.exception(
                    "Manejador %r falló para el evento %s; los demás continúan",
                    suscripcion.label, event_name)
        return atendidos

    def unsubscribe(self, event_name: str, handler: Callable[[dict], Any]) -> bool:
        """Retira UNA suscripción. True si estaba.

        Hace falta de verdad: una pantalla que se cierra debe dejar de recibir
        eventos, o seguirá reaccionando a cambios sobre widgets ya destruidos.
        """
        with self._lock:
            suscripciones = self._subscriptions.get(str(event_name))
            if not suscripciones:
                return False
            quedan = [s for s in suscripciones if s.handler is not handler]
            if len(quedan) == len(suscripciones):
                return False
            self._subscriptions[str(event_name)] = quedan
            return True

    def unsubscribe_all(self) -> None:
        """Vacía el bus. Para pruebas: un bus de proceso conserva estado entre
        casos y una suscripción olvidada haría fallar al siguiente."""
        with self._lock:
            self._subscriptions.clear()
            self._sequence = 0

    def subscriptions_for(self, event_name: str) -> tuple[str, ...]:
        """Etiquetas suscritas a un evento, en orden de entrega. Diagnóstico."""
        with self._lock:
            return tuple(s.label for s in self._subscriptions.get(str(event_name), ()))


_bus: ApplicationEventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> ApplicationEventBus:
    """El bus del proceso.

    Único a propósito: suscriptor y publicador se cablean en sitios distintos
    —el arranque suscribe, las rutas publican— y con instancias separadas cada
    publicación caería en el vacío sin que nada fallara.
    """
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = ApplicationEventBus()
    return _bus


def reset_bus() -> None:
    """Descarta el bus del proceso. Para pruebas."""
    global _bus
    with _bus_lock:
        _bus = None
