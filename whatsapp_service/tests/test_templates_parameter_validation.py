"""SET-20 repegado — `send_event_template()` no longer silently defaults
a missing template parameter to an empty string; it refuses the send.
Reimplements (not imports) the same rule
`backend/domain/notifications/policies/template_parameter_policy.py::
assert_params_satisfied()` documents — this microservice is independent
(CLAUDE.md §14).
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import messaging.templates as templates_mod  # noqa: E402


def _send(event_name: str, params: dict, *, to: str = "5551234567"):
    with patch.object(templates_mod, "send_template", new=AsyncMock(return_value=True)) as mock_send:
        result = asyncio.run(templates_mod.send_event_template(to, event_name, params))
        return result, mock_send


class TestSendEventTemplateParameterValidation:
    def test_complete_params_sends_normally(self):
        ok, mock_send = _send("pedido_confirmado", {"folio": "F1", "total": "$100.00"})
        assert ok is True
        assert mock_send.called is True

    def test_missing_param_refuses_to_send(self):
        ok, mock_send = _send("pedido_confirmado", {"folio": "F1"})
        assert ok is False
        assert mock_send.called is False

    def test_all_params_missing_refuses_to_send(self):
        ok, mock_send = _send("pedido_confirmado", {})
        assert ok is False
        assert mock_send.called is False

    def test_blank_string_param_counts_as_missing(self):
        """A caller passing `""` explicitly is exactly the case the
        original bug produced — must be refused just like an absent key."""
        ok, mock_send = _send("pedido_confirmado", {"folio": "F1", "total": ""})
        assert ok is False
        assert mock_send.called is False

    def test_template_with_no_declared_params_always_sends(self):
        ok, mock_send = _send("pedido_listo", {"folio": "F1"})
        assert ok is True
        assert mock_send.called is True

    def test_unknown_event_still_refuses_unchanged_behavior(self):
        ok, mock_send = _send("no_existe_este_evento", {})
        assert ok is False
        assert mock_send.called is False

    def test_every_real_caller_in_this_service_still_passes_complete_params(self):
        """Regression guard: the 3 real call sites in this service
        (notifications/customer.py, notifications/rrhh.py) always supply
        every declared param today — this new validation must never
        reject any of them."""
        real_calls = [
            ("pedido_confirmado", {"folio": "F1", "total": "$1.00"}),
            ("pedido_listo", {"folio": "F1"}),
            ("anticipo_requerido", {"folio": "F1", "monto": "$1.00", "link_pago": "https://x"}),
            ("pago_recibido", {"folio": "F1", "monto": "$1.00"}),
            ("entrega_en_camino", {"folio": "F1"}),
            ("recordatorio_anticipo", {"folio": "F1", "fecha_entrega": "2026-09-01"}),
            ("rrhh_vacaciones", {"nombre": "Ana", "fecha_inicio": "2026-09-01", "fecha_fin": "2026-09-05"}),
            ("rrhh_nomina", {"nombre": "Ana", "periodo": "Agosto 2026"}),
        ]
        for event_name, params in real_calls:
            ok, mock_send = _send(event_name, params)
            assert ok is True, f"{event_name} should have sent with real params {params}"
            assert mock_send.called is True
