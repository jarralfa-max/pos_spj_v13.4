from __future__ import annotations
from parser.intent_parser import ParsedIntent


def map_ai_to_parsed_intent(ai_result) -> ParsedIntent:
    mapping = {
        "create_order": "pedido",
        "schedule_order": "pedido",
        "create_quote": "cotizacion",
        "accept_quote": "accept_quote",
        "reject_quote": "reject_quote",
        "change_branch": "change_branch",
        "accept_adjustment": "accept_adjustment",
        "reject_adjustment": "reject_adjustment",
        "cancel_order": "cancel",
    }
    intent_name = mapping.get(str(ai_result.intent.value), "unknown")
    parsed = ParsedIntent(intent=intent_name, confidence=float(ai_result.confidence), source="ai")
    parsed.products = [
        {
            "nombre": p.product_name,
            "cantidad_solicitada": p.quantity,
            "unidad_solicitada": p.unit,
            "notas": p.notes,
        }
        for p in ai_result.products
    ]
    parsed.workflow_type = ai_result.workflow_type.value
    parsed.delivery_type = ai_result.delivery_type.value
    parsed.branch_reference = ai_result.branch_reference
    parsed.scheduled_at = ai_result.scheduled_at
    parsed.quote_reference = ai_result.quote_reference
    parsed.order_reference = ai_result.order_reference
    parsed.adjustment_response = ai_result.adjustment_response.value
    parsed.needs_clarification = ai_result.needs_clarification
    parsed.clarification_question = ai_result.clarification_question
    return parsed

