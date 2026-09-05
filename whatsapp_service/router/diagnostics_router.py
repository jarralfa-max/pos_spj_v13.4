# router/diagnostics_router.py — WA-20 (§58 del prompt maestro)
"""
`GET /diagnostics` — métricas numéricas de operación del canal
(`DiagnosticsService`, WA-20), complementando `/health` (WA-4). Protegido
con la misma autenticación interna que `/api/notify/*` (WA-1) — a
diferencia de `/health` (público, consumido por monitoreo externo/`WhatsAppClient.health_check()`),
`/diagnostics` expone volumen operativo/de negocio (conversaciones,
mensajes, colas), así que no es público.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from middleware.service_auth import require_service_auth

router = APIRouter(tags=["diagnostics"], dependencies=[Depends(require_service_auth)])


@router.get("/diagnostics")
async def diagnostics(request: Request):
    root = getattr(request.app.state, "composition_root", None)
    if root is None:
        raise HTTPException(status_code=503, detail="CompositionRoot no disponible todavía")
    return root.diagnostics_service.get_metrics()
