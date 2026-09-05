# tests/test_intent_resolution_value_objects.py — WA-8
from __future__ import annotations

from domain.whatsapp.enums import Intent
from domain.whatsapp.value_objects.intent_resolution import (
    EntityValidationStatus,
    IntentEntity,
    IntentResolution,
    IntentResolutionSource,
)


class TestIntentEntity:
    def test_defaults(self):
        entity = IntentEntity(name="product", value="bistec")
        assert entity.normalized_value is None
        assert entity.confidence == 1.0
        assert entity.validation_status == EntityValidationStatus.UNVALIDATED

    def test_is_frozen(self):
        entity = IntentEntity(name="product", value="bistec")
        try:
            entity.value = "otro"  # type: ignore[misc]
            assert False, "se esperaba FrozenInstanceError"
        except Exception:
            pass


class TestIntentResolution:
    def test_is_resolved_true_for_real_sources(self):
        resolution = IntentResolution(intent=Intent.GREETING, confidence=0.7, source=IntentResolutionSource.RULE)
        assert resolution.is_resolved is True

    def test_is_resolved_false_for_unresolved(self):
        resolution = IntentResolution(intent=Intent.HUMAN_HANDOFF, confidence=0.0, source=IntentResolutionSource.UNRESOLVED)
        assert resolution.is_resolved is False

    def test_entities_default_to_empty_tuple(self):
        resolution = IntentResolution(intent=Intent.GREETING, confidence=0.7, source=IntentResolutionSource.RULE)
        assert resolution.entities == ()
