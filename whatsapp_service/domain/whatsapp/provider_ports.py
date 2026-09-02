# domain/whatsapp/provider_ports.py — WA-2 (corregido en WA-5)
"""
Puerto (interfaz) del proveedor de mensajería (§22 del prompt maestro).
Solo el contrato — la implementación concreta
(`infrastructure/providers/meta_cloud_api/gateway.py::MetaCloudApiWhatsAppGateway`)
es WA-5. Ningún flow/router debe depender de `httpx`/proveedor directamente;
siempre a través de este puerto.

**Corrección WA-5**: los métodos que hablan con la Graph API se declaran
`async def` — el propio `messaging/sender.py` (el sender real y en
producción que WA-5 reutiliza, no duplica) ya es 100% async sobre
`httpx.AsyncClient`, y todo el pipeline que llamará a este puerto (webhook,
flows) también lo es. `health_check()` es la única excepción deliberada:
sigue siendo síncrono porque `bootstrap/health_checks.py` (WA-4) es un
agregador síncrono, y un ping de salud liviano no justifica volver async
todo ese módulo.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class WhatsAppProviderGateway(Protocol):
    async def send_text(self, *, to: str, body: str) -> Dict[str, Any]: ...

    async def send_template(
        self, *, to: str, template_name: str, language: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    async def send_interactive(self, *, to: str, payload: Dict[str, Any]) -> Dict[str, Any]: ...

    async def send_media(self, *, to: str, media_type: str, media_reference: str) -> Dict[str, Any]: ...

    async def mark_read(self, *, provider_message_id: str) -> None: ...

    async def download_media(self, *, media_id: str) -> bytes: ...

    async def get_message_status(self, *, provider_message_id: str) -> Optional[str]: ...

    def health_check(self) -> bool: ...
