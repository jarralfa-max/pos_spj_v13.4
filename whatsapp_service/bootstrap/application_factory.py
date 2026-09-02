# bootstrap/application_factory.py — WA-4 (§7 del prompt maestro)
"""
WhatsAppApplicationFactory — construye una app FastAPI mínima a partir del
CompositionRoot (§7: "main.py debe limitarse a: crear FastAPI, invocar
ApplicationFactory, registrar lifespan, registrar routers canónicos").

**Todavía NO es el entrypoint real del microservicio.** `whatsapp_service/main.py`
sigue siendo la app en producción — expone el webhook oficial de Meta, el
webhook de MercadoPago, y los routers `notify`/`delivery` que WA-1 ya
aseguró, todos construidos sobre piezas (ERPBridge, MessageRouter,
IntentParser, flows/) que las fases WA-5 a WA-9 todavía no reemplazan. Esta
factory expone hoy únicamente lo que WA-2/WA-3/WA-4 ya construyeron: salud
del canal. Cuando WA-5 (Provider Gateway), WA-6 (Webhook) y las fases
siguientes existan, `main.py` se reducirá a llamar
`WhatsAppApplicationFactory().create()` y esta se volverá el entrypoint
real — hasta entonces, coexisten (mismo patrón "nuevo en paralelo, sin
cortar lo viejo" que domain/schema ya establecieron en WA-2/WA-3).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from bootstrap.health_checks import build_health_response
from bootstrap.lifecycle import start_composition_root, stop_composition_root


class WhatsAppApplicationFactory:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def create(self) -> FastAPI:
        db_path = self._db_path

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            root = start_composition_root(db_path)
            app.state.composition_root = root
            yield
            stop_composition_root(root)

        app = FastAPI(
            title="SPJ POS — WhatsApp Channel (WA-4 bootstrap)",
            version="0.1.0",
            lifespan=lifespan,
        )

        @app.get("/health")
        async def health():
            return build_health_response(app.state.composition_root)

        return app
