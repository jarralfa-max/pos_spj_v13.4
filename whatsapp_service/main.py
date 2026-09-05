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


# ── Gate de arranque en producción (WA-1) ───────────────────────────────────────
def _assert_production_secrets_configured() -> None:
    """Aborta el arranque si faltan secretos críticos en producción.

    Antes de WA-1 (whatsapp_security_audit.md, §2/S4) no existía ningún
    chequeo de arranque que exigiera `WA_APP_SECRET`/`WA_INTERNAL_API_KEY`/etc.
    en producción — el proyecto ya tenía este patrón implementado para un
    tipo de riesgo distinto (`erp/bridge.py::_assert_sqlite_write_allowed`,
    escrituras SQLite bloqueadas en producción sin `ERP_API_URL`), pero nunca
    se aplicó a los secretos de webhook/auth. Se extrae como función standalone
    (en vez de código inline en `lifespan()`) específicamente para poder
    testearla sin levantar el FastAPI app/DB/migraciones completos.

    Sin `MP_ACCESS_TOKEN` configurado, MercadoPago no está en uso, así que no
    se exige `MP_WEBHOOK_SECRET` en ese caso.
    """
    from config.settings import (
        is_production,
        get_meta_access_token,
        get_meta_phone_number_id,
        get_verify_token,
        get_app_secret,
        get_internal_api_key,
        get_mp_webhook_secret,
        MP_ACCESS_TOKEN,
    )

    if not is_production():
        return

    required = {
        "WA_ACCESS_TOKEN (get_meta_access_token)": get_meta_access_token(),
        "WA_PHONE_NUMBER_ID (get_meta_phone_number_id)": get_meta_phone_number_id(),
        "WA_VERIFY_TOKEN (get_verify_token)": get_verify_token(),
        "WA_APP_SECRET (get_app_secret)": get_app_secret(),
        "WA_INTERNAL_API_KEY (get_internal_api_key)": get_internal_api_key(),
    }
    if MP_ACCESS_TOKEN:
        required["MP_WEBHOOK_SECRET (get_mp_webhook_secret)"] = get_mp_webhook_secret()

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "No se puede arrancar en producción: faltan secretos críticos de "
            "seguridad del canal WhatsApp: " + ", ".join(missing) + ". "
            "Configúralos desde el módulo WhatsApp (BD, configuraciones.wa_*) "
            "o variables de entorno antes de reintentar el arranque."
        )


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown del microservicio."""
    logger.info("=" * 60)
    logger.info("WhatsApp Service para SPJ POS — iniciando...")

    # WA-1: aborta el arranque en producción si faltan secretos críticos,
    # ANTES de tocar migraciones/DB/routers.
    _assert_production_secrets_configured()

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

    # 1b. CompositionRoot del canal (WA-4) — reutiliza la MISMA conexión
    # `erp.db` (ya migrada arriba), no abre una segunda. Cubre hoy los 6
    # repositorios SQLite de WA-2/WA-3; el resto de §8 (Provider Gateway,
    # Webhook Processor, etc.) llega en fases posteriores — ver la tabla en
    # `bootstrap/composition_root.py`. No reemplaza nada de lo que ya se
    # construye abajo (ERPBridge/MessageRouter/flows/): coexiste en
    # paralelo, igual que el esquema WA-3 coexiste con las tablas legacy.
    from bootstrap.composition_root import WhatsAppCompositionRoot
    from bootstrap.dependency_graph_validator import validate_composition_root
    composition_root = WhatsAppCompositionRoot(erp.db)
    validate_composition_root(composition_root)

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
    # Sin sucursal por default (REGLA CERO): el flujo fija la sucursal real
    # (UUIDv7) por mensaje vía matcher.set_sucursal(ctx.sucursal_id).
    matcher = ProductMatcher(erp.db, sucursal_id="")
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
    app.state.composition_root = composition_root

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
from router.notify_dispatch_router import router as notify_dispatch_router
from router.delivery_router import router as delivery_router
from router.diagnostics_router import router as diagnostics_router

app.include_router(wa_router)
app.include_router(mp_router)
app.include_router(notify_router)
# WA-18: montado ADITIVAMENTE junto al notify_router legacy (prefijo
# /api/notify/v2, sin colisión) — ver docstring de notify_dispatch_router.py.
app.include_router(notify_dispatch_router)
app.include_router(delivery_router)
# WA-20: GET /diagnostics — métricas de operación, complementa /health.
app.include_router(diagnostics_router)


# ── Health check (WA-4, §58) ────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check real (WA-4) — database/schema/secrets hoy; los
    subsistemas que otras fases todavía no construyen (Provider Gateway,
    workers de inbox/outbox, API ERP) se reportan UNKNOWN explícitamente,
    nunca como HEALTHY falso. `service`/`erp_connected` se conservan para
    compatibilidad con `WhatsAppClient.health_check()` (ERP-side), que solo
    verifica que la respuesta no sea `None` — no depende de la forma
    exacta."""
    if not hasattr(app.state, "composition_root"):
        return {"status": "UNKNOWN", "service": "whatsapp-service", "erp_connected": False, "checks": []}

    from bootstrap.health_checks import build_health_response

    response = build_health_response(app.state.composition_root)
    response["service"] = "whatsapp-service"
    response["erp_connected"] = hasattr(app.state, "erp")
    return response


@app.get("/")
async def root():
    return {
        "service": "SPJ POS WhatsApp Service",
        "version": "1.0.0",
        "docs": "/docs",
    }
