# api/deps.py — Inyección de dependencias FastAPI
"""
Provee los servicios del ERP a los routers via FastAPI Depends.
El AppContainer vive en app.state; los routers lo reciben sin importarlo.
"""
from __future__ import annotations
from fastapi import Request, HTTPException, status


def get_container(request: Request):
    """Retorna el AppContainer inyectado en lifespan."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERP container no inicializado",
        )
    return container


def get_db(request: Request):
    """Retorna la conexión DB del container."""
    container = get_container(request)
    return container.db


def get_sales_service(request: Request):
    container = get_container(request)
    svc = getattr(container, "sales_service", None)
    if not svc:
        raise HTTPException(503, "SalesService no disponible")
    return svc


def get_uc_venta(request: Request):
    container = get_container(request)
    uc = getattr(container, "uc_venta", None)
    if not uc:
        raise HTTPException(503, "ProcesarVentaUC no disponible")
    return uc
