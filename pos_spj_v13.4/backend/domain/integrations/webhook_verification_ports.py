"""WebhookSignatureVerifierPort — SET-19 "Webhooks": the contract for
verifying an inbound webhook's signature per its `WebhookSignatureScheme`.
Implemented for real by
`backend/infrastructure/integrations/webhook_signature_verifier.py::
WebhookSignatureVerifier` — unlike `rendering_ports.DocumentRendererPort`
(SET-11) or `gateway_ports.CustomerDisplayGatewayPort` (SET-17), this one
gets a real implementation: HMAC verification is stateless, well-specified
crypto with no hardware/vendor dependency to validate against, the same
"safe to build for real" judgment SET-12 made for print routing.
"""

from __future__ import annotations

from typing import Protocol

from backend.domain.integrations.enums import WebhookSignatureScheme


class WebhookSignatureVerifierPort(Protocol):
    def verify(
        self, *, scheme: WebhookSignatureScheme, headers: dict, body: bytes, secret: str,
    ) -> bool:
        """Return True only if `body`'s signature (found in `headers`)
        is valid for `secret` under `scheme`. Must return False rather
        than raise for a malformed/absent signature header — an invalid
        signature is an expected, not exceptional, outcome."""
        ...
