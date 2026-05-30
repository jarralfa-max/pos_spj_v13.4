# main.py — WhatsApp Microservice for SPJ POS ERP
"""
FastAPI gateway — punto de entrada del microservicio.

Arrancar desde la carpeta whatsapp_service:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Arrancar desde la raíz del repositorio:
    uvicorn whatsapp_service.main:app --host 0.0.0.0 --port 8000 --reload

Producción:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI


# ── Configurar Python path ANTES de importar config/router/flows ───────────────
#
# Hay dos paquetes llamados `application` en el repo:
#   - whatsapp_service/application
#   - pos_spj_v13.4/application
#
# Si el ERP queda antes que whatsapp_service en sys.path, este import falla:
#   from application.confirm_order_use_case import ...
# porque Python resuelve `application` contra pos_spj_v13.4/application.
#
# Regla de arranque del microservicio:
#   1) whatsapp_service siempre debe ir primero.
#   2) pos_spj_v13.4 debe ir después, solo para imports ERP/migrations/core.
WA_SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WA_SERVICE_ROOT.parent
ERP_APP_ROOT = REPO_ROOT / "pos_spj_v13.4"


def _prioritize_path(path: Path, index: int) -> None:
    """Inserta un path en una posición estable, removiendo duplicados previos."""
    path_str = str(path)
    sys.path[:] = [p for p in sys.path if p != path_str]
    sys.path.insert(index, path_str)


_prioritize_path(WA_SERVICE_ROOT, 0)
if ERP_APP_ROOT.exists():
    _prioritize_path(ERP_APP_ROOT, 1)


# ── Logging ───────────────────────────────────────────────────────────────────
from config.settings import LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wa.main")


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown del microservicio."""
    logger.info("=" * 60)
    logger.info("WhatsApp Service para SPJ POS — iniciando...")

    from config.settings import ERP_DB_PATH, CONTEXT_DB_PATH

    # 0. Ejecutar migraciones del ERP (crear tablas si no existen)
    try:
        import sqlite3
        mig_conn = sqlite3.connect(ERP_DB_PATH)
        from migrations.engine import up as run_migrations
        run_migrations(mig_conn)
        mig_conn.close()
        logger.info("Migraciones del ERP aplicadas")
    except Exception as e:
        logger.warning("No se pudieron aplicar migraciones del ERP: %s", e)

    # 1. Conectar al ERP
    from erp.bridge import ERPBridge
    erp = ERPBridge(ERP_DB_PATH)
    logger.info("ERP conectado: %s", ERP_DB_PATH)

    # 2. EventBus
    from erp.events import WAEventEmitter
    events = WAEventEmitter(erp.db)
    events.ensure_tables()

    # 3. State store
    from state.conversation import ConversationStore
    store = ConversationStore(CONTEXT_DB_PATH)

    # 4. Product matcher + LLM + Intent parser
    from parser.product_matcher import ProductMatcher
    from parser.llm_local import OllamaClient
    from parser.intent_parser import IntentParser
    matcher = ProductMatcher(erp.db, sucursal_id=1)
    llm = OllamaClient()
    parser = IntentParser(matcher, llm_client=llm)

    # 5. Number registry
    from config.numbers import NumberRegistry
    number_registry = NumberRegistry(erp.db)

    # 6. Schedules
    from config.schedules import ScheduleService
    schedules = ScheduleService(erp.db)

    # 7. Handoff
    from middleware.handoff import HandoffService
    handoff = HandoffService(erp)

    # 8. Routers
    from router.number_router import NumberRouter
    from router.message_router import MessageRouter
    number_router = NumberRouter(number_registry)
    message_router = MessageRouter(
        erp=erp, store=store, parser=parser,
        events=events, schedules=schedules, handoff=handoff)

    # 9. Inyectar en webhooks
    from webhook.whatsapp import init_webhook
    init_webhook(message_router, number_router, store)

    from webhook.mercadopago import init_mp_webhook
    init_mp_webhook(erp, events)

    # Guardar refs globales para health check
    app.state.erp = erp
    app.state.store = store

    logger.info("WhatsApp Service listo ✅")
    logger.info("=" * 60)

    yield  # ── App corriendo ──

    # Shutdown
    logger.info("Cerrando WhatsApp Service...")
    erp.close()
    logger.info("WhatsApp Service cerrado.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SPJ POS — WhatsApp Service",
    version="1.0.0",
    description="Microservicio de WhatsApp para ERP SPJ POS v13.4",
    lifespan=lifespan,
)

# ── Registrar routers ─────────────────────────────────────────────────────────
from webhook.whatsapp import router as wa_router
from webhook.mercadopago import router as mp_router
from router.notify_router import router as notify_router
from router.delivery_router import router as delivery_router

app.include_router(wa_router)
app.include_router(mp_router)
app.include_router(notify_router)
app.include_router(delivery_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "whatsapp-service",
        "erp_connected": hasattr(app.state, "erp"),
    }


@app.get("/")
async def root():
    return {
        "service": "SPJ POS WhatsApp Service",
        "version": "1.0.0",
        "docs": "/docs",
    }
