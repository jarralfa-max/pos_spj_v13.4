"""
tests/test_eventbus_strict.py — FASE 1 ERP Refactor

Verifica que EventBus.publish(strict=True) relanza excepciones de handlers,
permitiendo rollback transaccional en operaciones críticas:
  - SALE_ITEMS_PROCESS
  - PRODUCTION_ITEMS_PROCESS
  - PURCHASE_ITEMS_PROCESS
  - TRANSFER_ITEMS_PROCESS

Verifica también que publish normal (strict=False) mantiene comportamiento
original: errores se loguean pero no se propagan.
"""
from __future__ import annotations

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.events.event_bus import EventBus, get_bus


# ── Fixture: bus limpio por cada test ────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_bus():
    """Limpia todos los handlers antes y después de cada test."""
    bus = get_bus()
    bus.clear_handlers()
    yield bus
    bus.clear_handlers()


# ── Helpers ───────────────────────────────────────────────────────────────────

class _SentinelError(RuntimeError):
    """Excepción distinguible para verificar que se relanzó."""


def _failing_handler(payload: dict) -> None:
    raise _SentinelError("handler intencional fallido")


def _ok_handler(payload: dict) -> None:
    payload["handled"] = True


# ── Tests publish normal (strict=False / default) ────────────────────────────

class TestPublishNormal:

    def test_ok_handler_ejecuta(self, clean_bus):
        result = {}

        def _h(p):
            result["ok"] = True

        clean_bus.subscribe("EVT_NORMAL", _h)
        clean_bus.publish("EVT_NORMAL", {})
        assert result.get("ok") is True

    def test_handler_falla_no_propaga(self, clean_bus):
        """publish normal debe absorber excepciones de handlers."""
        clean_bus.subscribe("EVT_NORMAL", _failing_handler)
        # No debe lanzar
        clean_bus.publish("EVT_NORMAL", {})

    def test_handler_falla_no_interrumpe_siguientes(self, clean_bus):
        """Cuando un handler falla en modo normal, los siguientes sí ejecutan."""
        result = {}

        def _bad(p):
            raise ValueError("fallo")

        def _good(p):
            result["reached"] = True

        # Prioridades: _bad primero (100), _good después (50)
        clean_bus.subscribe("EVT_MULTI", _bad,  priority=100)
        clean_bus.subscribe("EVT_MULTI", _good, priority=50)

        clean_bus.publish("EVT_MULTI", {})
        assert result.get("reached") is True

    def test_sin_handlers_es_noop(self, clean_bus):
        """Publicar un evento sin handlers no lanza."""
        clean_bus.publish("EVT_HUERFANO", {"dato": 1})

    def test_async_no_acepta_strict(self, clean_bus):
        """strict=True + async_=True debe rechazarse con ValueError."""
        clean_bus.subscribe("EVT_X", _ok_handler)
        with pytest.raises(ValueError, match="strict"):
            clean_bus.publish("EVT_X", {}, async_=True, strict=True)


# ── Tests publish strict ──────────────────────────────────────────────────────

class TestPublishStrict:

    def test_ok_handler_ejecuta_normalmente(self, clean_bus):
        """publish strict no rompe handlers exitosos."""
        result = {}

        def _h(p):
            result["ok"] = True

        clean_bus.subscribe("EVT_STRICT", _h)
        clean_bus.publish("EVT_STRICT", {}, strict=True)
        assert result.get("ok") is True

    def test_handler_falla_relanza(self, clean_bus):
        """publish strict debe relanzar la excepción del handler."""
        clean_bus.subscribe("EVT_STRICT", _failing_handler)

        with pytest.raises(_SentinelError):
            clean_bus.publish("EVT_STRICT", {}, strict=True)

    def test_handler_falla_interrumpe_siguiente(self, clean_bus):
        """En modo strict el primer handler que falla detiene la cadena."""
        result = {}

        def _bad(p):
            raise _SentinelError("primer handler falla")

        def _second(p):
            result["second_reached"] = True

        clean_bus.subscribe("EVT_STRICT", _bad,    priority=100)
        clean_bus.subscribe("EVT_STRICT", _second, priority=50)

        with pytest.raises(_SentinelError):
            clean_bus.publish("EVT_STRICT", {}, strict=True)

        assert "second_reached" not in result, (
            "El segundo handler no debe ejecutar cuando el primero falla en strict"
        )

    def test_sin_handlers_strict_es_noop(self, clean_bus):
        """publish strict sin handlers no lanza."""
        clean_bus.publish("EVT_HUERFANO_STRICT", {}, strict=True)

    def test_payload_enriched_llega_al_handler(self, clean_bus):
        """event_type debe inyectarse en el payload antes de llamar al handler."""
        received = {}

        def _h(p):
            received.update(p)

        clean_bus.subscribe("EVT_ENRICH", _h)
        clean_bus.publish("EVT_ENRICH", {"dato": 42}, strict=True)

        assert received.get("event_type") == "EVT_ENRICH"
        assert received.get("dato") == 42

    def test_excepcion_original_preservada(self, clean_bus):
        """El tipo exacto de excepción del handler se preserva al relanzar."""
        class _MyDomainError(Exception):
            pass

        def _h(p):
            raise _MyDomainError("error de dominio")

        clean_bus.subscribe("EVT_DOMAIN", _h)
        with pytest.raises(_MyDomainError):
            clean_bus.publish("EVT_DOMAIN", {}, strict=True)


# ── Tests de rollback transaccional simulado ──────────────────────────────────

class TestRollbackSimulado:
    """
    Simula el patrón usado en producción:
    1. Abrir transacción (flag committed=False)
    2. Hacer trabajo de DB
    3. publish(strict=True) — si falla, la excepción permite al caller hacer rollback
    4. Verificar que committed permanece False cuando el handler falla
    """

    def test_produccion_rollback_si_inventario_falla(self, clean_bus):
        """
        Si el handler de inventario en PRODUCTION_ITEMS_PROCESS falla,
        la producción NO debe quedar registrada.
        """
        from core.events.domain_events import PRODUCTION_ITEMS_PROCESS

        db_state = {"produccion_insertada": False, "inventario_actualizado": False}

        def _inventory_handler_que_falla(p):
            raise _SentinelError("inventario sin stock")

        clean_bus.subscribe(PRODUCTION_ITEMS_PROCESS, _inventory_handler_que_falla, priority=100)

        try:
            db_state["produccion_insertada"] = True  # simula INSERT producciones
            clean_bus.publish(PRODUCTION_ITEMS_PROCESS, {"conn": None}, strict=True)
            db_state["inventario_actualizado"] = True  # nunca debe llegar aquí
        except _SentinelError:
            db_state["produccion_insertada"] = False  # simula ROLLBACK
        except Exception:
            db_state["produccion_insertada"] = False

        assert not db_state["produccion_insertada"], (
            "Con strict=True y fallo de inventario, el rollback debe revertir la inserción"
        )
        assert not db_state["inventario_actualizado"]

    def test_venta_rollback_si_inventario_falla(self, clean_bus):
        """
        Si el handler de inventario en SALE_ITEMS_PROCESS falla,
        la venta NO debe quedar registrada.
        """
        from core.events.domain_events import SALE_ITEMS_PROCESS

        db_state = {"venta_insertada": False}

        def _inv_handler_falla(p):
            raise _SentinelError("sin stock")

        clean_bus.subscribe(SALE_ITEMS_PROCESS, _inv_handler_falla, priority=100)

        try:
            db_state["venta_insertada"] = True
            clean_bus.publish(SALE_ITEMS_PROCESS, {"items": []}, strict=True)
        except _SentinelError:
            db_state["venta_insertada"] = False  # simula SAVEPOINT ROLLBACK
        except Exception:
            db_state["venta_insertada"] = False

        assert not db_state["venta_insertada"]

    def test_compra_rollback_si_inventario_falla(self, clean_bus):
        from core.events.domain_events import PURCHASE_ITEMS_PROCESS

        db_state = {"compra_insertada": False}

        def _inv_handler_falla(p):
            raise _SentinelError("error al ingresar stock")

        clean_bus.subscribe(PURCHASE_ITEMS_PROCESS, _inv_handler_falla, priority=100)

        try:
            db_state["compra_insertada"] = True
            clean_bus.publish(PURCHASE_ITEMS_PROCESS, {"items": []}, strict=True)
        except _SentinelError:
            db_state["compra_insertada"] = False
        except Exception:
            db_state["compra_insertada"] = False

        assert not db_state["compra_insertada"]

    def test_transfer_rollback_si_inventario_falla(self, clean_bus):
        from core.events.domain_events import TRANSFER_ITEMS_PROCESS

        db_state = {"traspaso_guardado": False}

        def _inv_handler_falla(p):
            raise _SentinelError("sin stock en origen")

        clean_bus.subscribe(TRANSFER_ITEMS_PROCESS, _inv_handler_falla, priority=100)

        try:
            db_state["traspaso_guardado"] = True
            clean_bus.publish(TRANSFER_ITEMS_PROCESS, {"movements": []}, strict=True)
        except _SentinelError:
            db_state["traspaso_guardado"] = False
        except Exception:
            db_state["traspaso_guardado"] = False

        assert not db_state["traspaso_guardado"]

    def test_handler_exitoso_antes_de_fallo_no_deshace_trabajo_propio(self, clean_bus):
        """
        El caller (servicio) es responsable del rollback de DB.
        Verificamos que strict=True propaga correctamente para que el caller
        pueda tomar la decisión de rollback.
        """
        result = {"h1_ran": False, "h2_ran": False}

        def _h1(p):
            result["h1_ran"] = True

        def _h2_falla(p):
            result["h2_ran"] = True
            raise _SentinelError("h2 falla")

        clean_bus.subscribe("EVT_TWO", _h1,       priority=100)
        clean_bus.subscribe("EVT_TWO", _h2_falla, priority=50)

        with pytest.raises(_SentinelError):
            clean_bus.publish("EVT_TWO", {}, strict=True)

        # h1 corrió antes de que h2 fallara
        assert result["h1_ran"] is True
        assert result["h2_ran"] is True


# ── Tests de prioridad en modo strict ────────────────────────────────────────

class TestPrioridadStrict:

    def test_handlers_en_orden_prioridad_descendente(self, clean_bus):
        order = []

        def _h100(p): order.append(100)
        def _h50(p):  order.append(50)
        def _h10(p):  order.append(10)

        clean_bus.subscribe("EVT_PRIO", _h10,  priority=10)
        clean_bus.subscribe("EVT_PRIO", _h100, priority=100)
        clean_bus.subscribe("EVT_PRIO", _h50,  priority=50)

        clean_bus.publish("EVT_PRIO", {}, strict=True)
        assert order == [100, 50, 10]

    def test_strict_falla_en_prioridad_media_detiene_baja(self, clean_bus):
        order = []

        def _h100(p): order.append(100)

        def _h50_falla(p):
            order.append(50)
            raise _SentinelError("falla en prio 50")

        def _h10(p): order.append(10)

        clean_bus.subscribe("EVT_PRIO2", _h100,      priority=100)
        clean_bus.subscribe("EVT_PRIO2", _h50_falla, priority=50)
        clean_bus.subscribe("EVT_PRIO2", _h10,       priority=10)

        with pytest.raises(_SentinelError):
            clean_bus.publish("EVT_PRIO2", {}, strict=True)

        assert 100 in order
        assert 50 in order
        assert 10 not in order, "Handler de prioridad 10 no debe ejecutar si prio 50 falló en strict"


# ── Test de compatibilidad hacia atrás ────────────────────────────────────────

class TestCompatibilidadHaciaAtras:

    def test_publish_sin_strict_no_rompe_codigo_existente(self, clean_bus):
        """Verificar que publish() sin argumentos extra mantiene firma original."""
        called = {}
        clean_bus.subscribe("EVT_BACK", lambda p: called.update({"ok": True}))
        clean_bus.publish("EVT_BACK", {"x": 1})
        assert called.get("ok") is True

    def test_publish_async_false_sin_strict_igual_que_antes(self, clean_bus):
        called = {}
        clean_bus.subscribe("EVT_ASYNC", lambda p: called.update({"ok": True}))
        clean_bus.publish("EVT_ASYNC", {}, async_=False)
        assert called.get("ok") is True

    def test_get_bus_retorna_mismo_singleton(self, clean_bus):
        bus1 = get_bus()
        bus2 = get_bus()
        assert bus1 is bus2
