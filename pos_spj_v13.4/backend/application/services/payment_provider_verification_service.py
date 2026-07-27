"""Payment provider verification service — keeps HTTP out of PyQt (FASE 8)."""

from __future__ import annotations

from backend.application.dto.diagnostics import DiagnosticResult

_MP_PAYMENT_METHODS_URL = "https://api.mercadopago.com/v1/payment_methods"


class PaymentProviderVerificationService:
    """Verifies a Mercado Pago access token; the UI only renders the result."""

    def verify_mercado_pago_token(self, token: str) -> DiagnosticResult:
        token = (token or "").strip()
        if not token:
            return DiagnosticResult.failure("Ingresa el Access Token primero.")
        try:
            import json
            import urllib.request

            request = urllib.request.Request(
                _MP_PAYMENT_METHODS_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read())
            if isinstance(data, list) and data:
                return DiagnosticResult.success(
                    f"Token válido — {len(data)} métodos de pago disponibles.",
                    methods=len(data),
                )
            return DiagnosticResult.failure("Respuesta inesperada del servidor.")
        except Exception as exc:  # explicit, traceable failure
            return DiagnosticResult.failure(f"Token inválido o sin conexión: {exc}")
