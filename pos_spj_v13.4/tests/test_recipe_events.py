# tests/test_recipe_events.py
"""Remediación E — RecipeService emite RECETA_CREADA / RECETA_ACTUALIZADA.

La UI de producción (modulos/produccion.py) se suscribe a estos canales para
refrescarse en caliente cuando cambia una receta. Antes nadie los emitía
(suscripción huérfana). Estos tests fijan la emisión desde el punto canónico de
escritura de recetas.
"""
from unittest.mock import MagicMock

import pytest

from core.events.event_bus import get_bus
from core.services.recipes.recipe_service import RecipeService


@pytest.fixture
def svc_and_events():
    bus = get_bus()
    received = []
    h_c = lambda p: received.append(("RECETA_CREADA", p))
    h_u = lambda p: received.append(("RECETA_ACTUALIZADA", p))
    bus.subscribe("RECETA_CREADA", h_c, label="test.receta_creada")
    bus.subscribe("RECETA_ACTUALIZADA", h_u, label="test.receta_actualizada")
    svc = RecipeService.__new__(RecipeService)  # bypass __init__/DB
    svc._repo = MagicMock()
    svc._repo.create.return_value = "recipe-123"
    try:
        yield svc, received
    finally:
        try: bus.unsubscribe("RECETA_CREADA", h_c)
        except Exception: pass
        try: bus.unsubscribe("RECETA_ACTUALIZADA", h_u)
        except Exception: pass


def test_create_recipe_emits_receta_creada(svc_and_events):
    svc, received = svc_and_events
    rid = RecipeService.create_recipe(svc, "Salsa", "prod1", [], "ana")
    assert rid == "recipe-123"
    assert any(evt == "RECETA_CREADA" and p.get("receta_id") == "recipe-123"
               for evt, p in received)


def test_update_recipe_emits_receta_actualizada(svc_and_events):
    svc, received = svc_and_events
    RecipeService.update_recipe(svc, "recipe-123", "Salsa v2", [], "ana")
    assert any(evt == "RECETA_ACTUALIZADA" and p.get("receta_id") == "recipe-123"
               for evt, p in received)


def test_deactivate_recipe_emits_receta_actualizada(svc_and_events):
    svc, received = svc_and_events
    RecipeService.deactivate_recipe(svc, "recipe-123", "ana")
    assert any(evt == "RECETA_ACTUALIZADA" for evt, p in received)
