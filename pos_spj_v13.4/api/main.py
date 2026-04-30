# api/main.py — Gateway REST del ERP SPJ POS
"""
Arranca el servidor API REST del ERP.

Arrancar (desarrollo):
    cd pos_spj_v13.4
    uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

Producción:
    uvicorn api.main:app --host 0.0.0.0 --port 8001 --workers 2

Autenticación: header X-API-Key con la clave configurada en
  - Variable de entorno ERP_API_KEY, o
  - tabla configuraciones WHERE clave='api_gateway_key'

Documentación interactiva disponible en /docs y /redoc.
"""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.parent  # pos_spj_v13.4/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spj.api")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa el AppContainer y lo inyecta en app.state."""
    logger.info("=" * 60)
    logger.info("SPJ POS ERP — API Gateway iniciando...")

    db_path = os.environ.get(
        "ERP_DB_PATH",
        str(_HERE / "pos_spj.db"),
    )

    try:
        from core.app_container import AppContainer
        container = AppContainer(db_path=db_path)
        app.state.container = container
        logger.info("AppContainer inicializado: %s", db_path)
    except Exception as e:
        logger.error("No se pudo inicializar AppContainer: %s", e)
        # Exponer una conexión directa como fallback mínimo
        from core.db.connection import get_connection
        app.state.container = _MinimalContainer(get_connection(db_path))
        logger.warning("Usando contenedor mínimo (sin servicios completos)")

    logger.info("API Gateway lista en /docs ✅")
    logger.info("=" * 60)

    yield  # ── Running ──

    logger.info("Cerrando API Gateway...")
    try:
        container = getattr(app.state, "container", None)
        if hasattr(container, "db"):
            container.db.close()
    except Exception:
        pass
    logger.info("API Gateway cerrada.")


class _MinimalContainer:
    """Contenedor mínimo cuando AppContainer no está disponible."""
    def __init__(self, db):
        self.db = db
        self.sales_service = None
        self.uc_venta = None
        self.app_service = None


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SPJ POS — ERP REST API",
    version="1.0.0",
    description=(
        "API REST del ERP SPJ POS. Requiere `X-API-Key` en todos los endpoints. "
        "Configura la clave en variable de entorno `ERP_API_KEY` o en "
        "`configuraciones.api_gateway_key`."
    ),
    lifespan=lifespan,
)

# CORS — ajustar origins en producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("API_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from api.routers.ventas import router as ventas_router
from api.routers.inventario import router as inventario_router
from api.routers.clientes import router as clientes_router
from api.routers.pedidos import router as pedidos_router

app.include_router(ventas_router,    prefix="/api/v1")
app.include_router(inventario_router, prefix="/api/v1")
app.include_router(clientes_router,  prefix="/api/v1")
app.include_router(pedidos_router,   prefix="/api/v1")


# ── Health / root ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["sistema"])
async def health():
    """Verifica estado del gateway y la conexión a la BD."""
    from fastapi import Request
    container = getattr(app.state, "container", None)
    db_ok = False
    if container:
        try:
            container.db.execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            pass
    return {
        "status":  "ok" if db_ok else "degraded",
        "db":      "connected" if db_ok else "error",
        "service": "erp-api-gateway",
        "version": "1.0.0",
    }


@app.get("/", tags=["sistema"])
async def root():
    return {
        "service": "SPJ POS ERP API Gateway",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
        "endpoints": [
            "/api/v1/ventas",
            "/api/v1/inventario",
            "/api/v1/clientes",
            "/api/v1/pedidos",
        ],
    }
