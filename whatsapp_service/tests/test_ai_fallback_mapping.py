from ai.intent_schema import AIIntentResult
from ai.fallback import map_ai_to_parsed_intent


def test_map_schedule_order_to_pedido_with_metadata():
    ai = AIIntentResult.model_validate({
        "intent": "schedule_order",
        "confidence": 0.9,
        "workflow_type": "scheduled",
        "delivery_type": "home_delivery",
        "scheduled_at": "2026-05-24T10:00:00",
        "products": [{"product_name": "pechuga", "quantity": 2, "unit": "kg", "notes": ""}],
    })
    parsed = map_ai_to_parsed_intent(ai)
    assert parsed.intent == "pedido"
    assert parsed.workflow_type == "scheduled"
    assert parsed.delivery_type == "home_delivery"
    assert parsed.scheduled_at.startswith("2026-05-24")
    assert parsed.products and parsed.products[0]["nombre"] == "pechuga"


def test_map_quote_and_adjustment_intents():
    quote = AIIntentResult.model_validate({"intent": "create_quote", "confidence": 0.88})
    acc = AIIntentResult.model_validate({"intent": "accept_adjustment", "confidence": 0.99})
    rej = AIIntentResult.model_validate({"intent": "reject_adjustment", "confidence": 0.99})
    assert map_ai_to_parsed_intent(quote).intent == "cotizacion"
    assert map_ai_to_parsed_intent(acc).intent == "accept_adjustment"
    assert map_ai_to_parsed_intent(rej).intent == "reject_adjustment"


def test_unknown_intent_keeps_safe_unknown():
    ai = AIIntentResult.model_validate({"intent": "unknown", "confidence": 0.2})
    parsed = map_ai_to_parsed_intent(ai)
    assert parsed.intent == "unknown"
