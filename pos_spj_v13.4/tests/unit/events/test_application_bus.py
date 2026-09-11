"""Bus de eventos de la aplicación.

Reemplaza `core/events/event_bus.py`. El contrato lo fijan sus consumidores
vivos —los tres despachadores de bandeja de salida y el cableado de Compras—,
que llaman `subscribe(nombre, handler, priority=, label=)` y
`publish(nombre, payload, async_=False)`.

La tabla de prioridades es la de CLAUDE.md, no una elección de este archivo.
"""
from __future__ import annotations

import pytest

from backend.shared.events.application_bus import (
    ApplicationEventBus,
    get_bus,
    reset_bus,
)

#: Las franjas que documenta CLAUDE.md.
SYNC, CRITICO, LEDGER, AUDITORIA, NOTIFICACION, ANALITICA = 100, 80, 50, 30, 10, 5


@pytest.fixture
def bus():
    return ApplicationEventBus()


@pytest.fixture(autouse=True)
def _bus_limpio():
    """Un bus de proceso conserva estado entre casos: una suscripción olvidada
    haría fallar al siguiente test por un motivo que no tiene que ver con él."""
    reset_bus()
    yield
    reset_bus()


# ── entrega ─────────────────────────────────────────────────────────────────
def test_a_subscriber_receives_the_payload(bus):
    recibido = {}
    bus.subscribe("VENTA_COMPLETADA", lambda p: recibido.update(p))
    bus.publish("VENTA_COMPLETADA", {"venta_id": "V-1"})
    assert recibido == {"venta_id": "V-1"}


def test_publishing_returns_how_many_handlers_ran(bus):
    bus.subscribe("X", lambda p: None)
    bus.subscribe("X", lambda p: None)
    assert bus.publish("X", {}) == 2


def test_an_event_nobody_listens_to_is_not_an_error(bus):
    """Publicar antes de que exista el suscriptor es lo normal en este
    repositorio: los manejadores se suscriben en su corte."""
    assert bus.publish("NADIE_ESCUCHA", {}) == 0


def test_handlers_cannot_mutate_each_others_payload(bus):
    """Cada manejador recibe el mismo diccionario; si uno lo alterara, el
    siguiente vería datos distintos de los que se publicaron."""
    original = {"total": 100}
    bus.subscribe("X", lambda p: p.update({"total": 999}), priority=SYNC)
    visto = {}
    bus.subscribe("X", lambda p: visto.update(p), priority=LEDGER)
    bus.publish("X", original)

    assert original == {"total": 100}, "el publicador no debe ver cambios"


# ── prioridades ─────────────────────────────────────────────────────────────
def test_higher_priority_runs_first(bus):
    """Si la analítica corriera antes que el ledger, informaría sobre un
    asiento que todavía no existe."""
    orden = []
    bus.subscribe("X", lambda p: orden.append("analitica"), priority=ANALITICA)
    bus.subscribe("X", lambda p: orden.append("ledger"), priority=LEDGER)
    bus.subscribe("X", lambda p: orden.append("sync"), priority=SYNC)

    bus.publish("X", {})
    assert orden == ["sync", "ledger", "analitica"]


def test_equal_priority_keeps_subscription_order(bus):
    """Determinista: si dependiera del orden de importación, el mismo evento
    se entregaría distinto según qué módulo se cargara antes."""
    orden = []
    for n in range(4):
        bus.subscribe("X", lambda p, _n=n: orden.append(_n), priority=CRITICO)
    bus.publish("X", {})
    assert orden == [0, 1, 2, 3]


def test_a_late_subscriber_takes_its_priority_place(bus):
    """Suscribirse después no relega al final si la prioridad es mayor."""
    orden = []
    bus.subscribe("X", lambda p: orden.append("auditoria"), priority=AUDITORIA)
    bus.subscribe("X", lambda p: orden.append("sync"), priority=SYNC)
    bus.publish("X", {})
    assert orden == ["sync", "auditoria"]


# ── fallos ──────────────────────────────────────────────────────────────────
def test_a_failing_handler_does_not_stop_the_others(bus):
    """Que la notificación de una venta falle no puede impedir que su asiento
    contable se escriba."""
    corridos = []

    def _falla(_payload):
        raise RuntimeError("el proveedor no responde")

    bus.subscribe("X", _falla, priority=NOTIFICACION, label="notificacion")
    bus.subscribe("X", lambda p: corridos.append("ledger"), priority=LEDGER)

    assert bus.publish("X", {}, strict=False) == 1
    assert corridos == ["ledger"]


def test_strict_mode_propagates_the_failure(bus):
    """Para quien necesite que el fallo aborte la operación."""
    def _falla(_payload):
        raise RuntimeError("boom")

    bus.subscribe("X", _falla)
    with pytest.raises(RuntimeError):
        bus.publish("X", {}, strict=True)


def test_a_failure_in_a_high_priority_handler_still_lets_the_rest_run(bus):
    corridos = []
    bus.subscribe("X", lambda p: (_ for _ in ()).throw(RuntimeError()), priority=SYNC)
    bus.subscribe("X", lambda p: corridos.append("despues"), priority=LEDGER)
    bus.publish("X", {}, strict=False)
    assert corridos == ["despues"]


# ── forma que esperan los despachadores ─────────────────────────────────────
def test_the_dispatcher_call_shape_is_accepted(bus):
    """Los tres despachadores llaman exactamente así."""
    recibido = []
    bus.subscribe("PEDIDO_LISTO", lambda p: recibido.append(p))
    bus.publish("PEDIDO_LISTO", {"event_id": "e1"}, async_=False)
    assert recibido == [{"event_id": "e1"}]


def test_async_is_accepted_but_delivery_is_synchronous(bus):
    """Los tres publican DENTRO de la transacción que generó el evento:
    entregar en otro hilo rompería esa atomicidad sin avisar. Se acepta el
    parámetro y se ignora, en vez de fingir que se respeta."""
    corridos = []
    bus.subscribe("X", lambda p: corridos.append(1))
    bus.publish("X", {}, async_=True)
    assert corridos == [1], "la entrega debe haber ocurrido ya al volver"


def test_the_wiring_call_shape_is_accepted(bus):
    """`wire_procurement` pasa `priority` y `label` por nombre."""
    bus.subscribe("X", lambda p: None, priority=LEDGER, label="procurement_cxp")
    assert bus.subscriptions_for("X") == ("procurement_cxp",)


# ── bus del proceso ─────────────────────────────────────────────────────────
def test_the_process_bus_is_the_same_everywhere():
    """Suscriptor y publicador se cablean en sitios distintos: con instancias
    separadas cada publicación caería en el vacío sin que nada fallara."""
    recibido = []
    get_bus().subscribe("X", lambda p: recibido.append(p))
    get_bus().publish("X", {"ok": True})
    assert recibido == [{"ok": True}]


def test_resetting_the_process_bus_clears_its_subscriptions():
    get_bus().subscribe("X", lambda p: None)
    reset_bus()
    assert get_bus().publish("X", {}) == 0


# ── retirar suscripciones ───────────────────────────────────────────────────
def test_unsubscribing_stops_delivery(bus):
    """Una pantalla que se cierra debe dejar de recibir eventos, o seguirá
    reaccionando a cambios sobre widgets ya destruidos."""
    recibido = []

    def _handler(payload):
        recibido.append(payload)

    bus.subscribe("X", _handler)
    assert bus.unsubscribe("X", _handler) is True
    bus.publish("X", {})
    assert recibido == []


def test_unsubscribing_leaves_the_other_handlers(bus):
    otros = []
    def _uno(_p): pass
    bus.subscribe("X", _uno)
    bus.subscribe("X", lambda p: otros.append(1))
    bus.unsubscribe("X", _uno)
    assert bus.publish("X", {}) == 1
    assert otros == [1]


def test_unsubscribing_something_never_subscribed_is_false(bus):
    assert bus.unsubscribe("X", lambda p: None) is False


# ── catálogo de productos ───────────────────────────────────────────────────
def test_a_catalog_change_emits_the_specific_event_and_the_refresh_signal():
    """Los dos, y no es redundancia: el concreto para quien reacciona a ese
    hecho, el de refresco para quien sólo necesita saber que su lista quedó
    vieja."""
    from backend.application.services.product_catalog_service import (
        _publish_catalog_change,
    )
    from backend.domain.products.events import ProductEvents

    visto = []
    get_bus().subscribe(ProductEvents.PRODUCT_CREATED, lambda p: visto.append("concreto"))
    get_bus().subscribe(ProductEvents.PRODUCTS_CHANGED, lambda p: visto.append("refresco"))

    _publish_catalog_change("created", product_id="P1", product_name="Arrachera",
                            active=True, operation_id="op1")
    assert visto == ["concreto", "refresco"]


def test_the_spanish_legacy_channel_is_no_longer_emitted():
    """Sus suscriptores vivían en `modulos/`, que ya no existe, y los nombres
    canónicos los reemplazan por declaración propia."""
    from backend.application.services.product_catalog_service import (
        _publish_catalog_change,
    )

    visto = []
    get_bus().subscribe("PRODUCTO_CREADO", lambda p: visto.append("legacy"))
    _publish_catalog_change("created", product_id="P1", product_name="X", active=True)
    assert visto == []


def test_an_unknown_catalog_action_publishes_nothing_and_does_not_raise():
    from backend.application.services.product_catalog_service import (
        _publish_catalog_change,
    )
    from backend.domain.products.events import ProductEvents

    visto = []
    get_bus().subscribe(ProductEvents.PRODUCTS_CHANGED, lambda p: visto.append(1))
    _publish_catalog_change("accion_inventada", product_id="P1", product_name="X",
                            active=True)
    assert visto == []


# ── paridad con el bus anterior ─────────────────────────────────────────────
# Estas conductas las fijaba `tests/test_eventbus_strict.py`, que importa
# `core.events.event_bus` y por tanto ya no se recoge. Se vuelven a fijar aquí
# contra el bus canónico en vez de darlas por heredadas: un contrato que no
# ejecuta nadie no es un contrato.


def test_strict_stops_the_chain_at_the_first_failure(bus):
    """En estricto el fallo ABORTA: los manejadores de menor prioridad no
    corren. Es la diferencia entera con `strict=False`, y sin prueba propia
    nada impediría que un `continue` mal puesto los siguiera ejecutando —
    justo el escenario que el modo estricto existe para evitar."""
    corridos = []
    bus.subscribe("X", lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
                  priority=CRITICO)
    bus.subscribe("X", lambda p: corridos.append("ledger"), priority=LEDGER)

    with pytest.raises(RuntimeError):
        bus.publish("X", {}, strict=True)
    assert corridos == [], "el manejador de menor prioridad no debia correr"


def test_strict_preserves_the_exact_exception_type(bus):
    """Quien publica en estricto distingue por tipo: envolver el fallo en otra
    excepción haría que su `except` específico dejara de coincidir y el error
    subiera hasta arriba como si fuera desconocido."""
    class ErrorDeInventario(Exception):
        pass

    bus.subscribe("X", lambda p: (_ for _ in ()).throw(
        ErrorDeInventario("sin existencias")))

    with pytest.raises(ErrorDeInventario, match="sin existencias"):
        bus.publish("X", {}, strict=True)


def test_strict_without_subscribers_is_not_an_error(bus):
    """Publicar en estricto antes de que exista el suscriptor no es un fallo:
    lo que estricto exige es que nadie falle EN SILENCIO, no que haya alguien."""
    assert bus.publish("NADIE_ESCUCHA", {}, strict=True) == 0


def test_strict_and_async_together_are_accepted(bus):
    """El bus anterior rechazaba esta combinación con ValueError, y tenía
    razón: no se puede relanzar hacia el publicador desde otro hilo. Aquí la
    entrega es SIEMPRE síncrona, así que la contradicción desapareció con el
    hilo. Se deja escrito el cambio en vez de heredar una prohibición que
    perdió su motivo."""
    bus.subscribe("X", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        bus.publish("X", {}, async_=True, strict=True)


def test_the_bus_does_not_inject_event_type_into_the_payload(bus):
    """El bus anterior añadía `event_type` a la carga antes de entregarla.
    Aquí NO, y a propósito: el productor ya pone `event_name` dentro, y el
    despachador de bandeja de salida lo valida contra su propia fila —si
    `payload["event_name"]` no coincide con `row["event_type"]` la fila se va
    a reintento. Inyectar un segundo campo con el mismo hecho daría dos
    fuentes para el mismo dato y nada garantizaría que concuerden."""
    visto = {}
    bus.subscribe("VENTA_COMPLETADA", lambda p: visto.update(p))
    bus.publish("VENTA_COMPLETADA", {"venta_id": "V-1"})
    assert visto == {"venta_id": "V-1"}
