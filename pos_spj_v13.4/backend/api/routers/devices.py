"""API central de equipos (auditoría enterprise, Fase 4).

* `POST /api/v1/devices/enroll` — vincular un equipo con un código de invitación y
  su llave pública. Sin autenticación previa (el código ES la autorización),
  limitado por IP.
* `GET /api/v1/devices/me` y `POST /api/v1/devices/heartbeat` — firmados por el
  equipo. `me` responde aunque el equipo esté suspendido o dado de baja: así la
  estación se entera de una revocación en cuanto tiene conexión.
* `/api/v1/admin/...` — administración de equipos e invitaciones. Firmados por una
  estación de ADMINISTRACIÓN; `X-SPJ-Actor-User` lleva el usuario que la pidió
  (su permiso lo validó la aplicación de esa estación).

Errores: `{"detail": {"code": ..., "message": ...}}`. 401 firma inválida; 403
equipo suspendido/dado de baja o estación sin administración; 400 regla de
negocio (código vencido, usado, revocado…).
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/v1", tags=["devices"])

MAX_BODY_BYTES = 64 * 1024


def _workflow(request: Request):
    flujo = getattr(request.app.state, "device_workflow", None)
    if flujo is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"code": "UNCONFIGURED", "message": "Servidor sin base de datos"})
    return flujo


async def _body(request: Request) -> bytes:
    cuerpo = await request.body()
    if len(cuerpo) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            {"code": "TOO_LARGE", "message": "Solicitud demasiado grande"})
    return cuerpo


def _json(cuerpo: bytes) -> dict:
    if not cuerpo:
        return {}
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            {"code": "BAD_JSON", "message": "JSON inválido"}) from None
    if not isinstance(datos, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            {"code": "BAD_JSON", "message": "Se esperaba un objeto"})
    return datos


def _path(request: Request) -> str:
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


async def _signed(request: Request, accion, *, require_active=True, admin=False):
    from backend.application.sync.device_provisioning import (
        DeviceNotAuthorizedError,
        ProvisioningError,
    )
    cuerpo = await _body(request)
    try:
        return _workflow(request).signed(
            method=request.method, path=_path(request), headers=request.headers, body=cuerpo,
            action=lambda servicio, estacion: accion(servicio, estacion, _json(cuerpo)),
            require_active=require_active,
            actor_user=request.headers.get("x-spj-actor-user") if admin else None)
    except DeviceNotAuthorizedError as exc:
        codigo = (status.HTTP_401_UNAUTHORIZED if exc.code == "BAD_SIGNATURE"
                  else status.HTTP_403_FORBIDDEN)
        raise HTTPException(codigo, {"code": exc.code, "message": str(exc)}) from None
    except ProvisioningError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            {"code": exc.code, "message": str(exc)}) from None


def _jsonable(valor):
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _jsonable(v) for k, v in valor.items() if k not in ("credential_hash",
                                                                       "token_hash")}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


@router.post("/devices/enroll")
async def enroll(request: Request) -> dict:
    from backend.application.sync.device_provisioning import ProvisioningError

    limitador = request.app.state.enroll_rate_limiter
    if not limitador.allow(request.client.host if request.client else "desconocido"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            {"code": "RATE_LIMITED", "message": "Demasiados intentos"},
                            headers={"Retry-After": "60"})
    datos = _json(await _body(request))
    try:
        vinculo = _workflow(request).enroll(
            code=str(datos.get("code") or ""), public_key=str(datos.get("public_key") or ""),
            app_version=str(datos.get("app_version") or ""),
            hostname=str(datos.get("hostname") or ""),
            expected_branch_id=str(datos.get("expected_branch_id") or "") or None)
    except ProvisioningError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            {"code": exc.code, "message": str(exc)}) from None
    return vinculo.to_dict()


@router.get("/devices/me")
async def me(request: Request) -> dict:
    return await _signed(request, lambda s, e, d: s.status_of(e), require_active=False)


@router.post("/devices/heartbeat")
async def heartbeat(request: Request) -> dict:
    def accion(servicio, estacion, datos):
        ultima = datos.get("last_sync_at")
        pendientes = datos.get("pending_events")
        return servicio.heartbeat(
            estacion, app_version=str(datos.get("app_version") or "") or None,
            pending_events=int(pendientes) if isinstance(pendientes, int) else None,
            last_sync_at=datetime.fromisoformat(ultima) if ultima else None)
    return await _signed(request, accion)


# ── administración ──────────────────────────────────────────────────────
@router.get("/admin/devices")
async def admin_devices(request: Request) -> dict:
    return {"devices": _jsonable(await _signed(
        request, lambda s, e, d: s.list_devices(actor_station=e), admin=True))}


@router.get("/admin/devices/{station_id}/history")
async def admin_history(station_id: str, request: Request) -> dict:
    return {"events": _jsonable(await _signed(
        request, lambda s, e, d: s.history(station_id, actor_station=e), admin=True))}


@router.post("/admin/devices/{station_id}/status")
async def admin_status(station_id: str, request: Request) -> dict:
    actor = request.headers.get("x-spj-actor-user")
    await _signed(request, lambda s, e, d: s.change_status(
        station_id, str(d.get("action") or ""), reason=str(d.get("reason") or ""),
        actor_station=e, actor_user=actor), admin=True)
    return {"ok": True}


@router.post("/admin/devices/{station_id}/reassign")
async def admin_reassign(station_id: str, request: Request) -> dict:
    actor = request.headers.get("x-spj-actor-user")
    await _signed(request, lambda s, e, d: s.reassign(
        station_id, branch_id=str(d.get("branch_id") or ""),
        reason=str(d.get("reason") or ""), actor_station=e, actor_user=actor), admin=True)
    return {"ok": True}


@router.get("/admin/invitations")
async def admin_invitations(request: Request) -> dict:
    return {"invitations": _jsonable(await _signed(
        request, lambda s, e, d: s.list_invitations(actor_station=e), admin=True))}


@router.post("/admin/invitations")
async def admin_create_invitation(request: Request) -> dict:
    actor = request.headers.get("x-spj-actor-user")

    def accion(servicio, estacion, d):
        emitida = servicio.create_invitation(
            branch_id=str(d.get("branch_id") or ""),
            workstation_type=str(d.get("workstation_type") or ""),
            capabilities=list(d.get("capabilities") or ()), kind=str(d.get("kind") or "NEW"),
            target_station_id=d.get("target_station_id") or None,
            display_name=str(d.get("display_name") or ""),
            ttl_minutes=int(d.get("ttl_minutes") or 30),
            grants_admin=bool(d.get("grants_admin")), actor_station=estacion,
            actor_user=actor)
        return {"invitation_id": emitida.invitation_id, "code": emitida.code,
                "expires_at": emitida.expires_at.isoformat(), "kind": emitida.kind}
    return await _signed(request, accion, admin=True)


@router.post("/admin/invitations/{invitation_id}/revoke")
async def admin_revoke_invitation(invitation_id: str, request: Request) -> dict:
    actor = request.headers.get("x-spj-actor-user")
    await _signed(request, lambda s, e, d: s.revoke_invitation(
        invitation_id, actor_station=e, actor_user=actor), admin=True)
    return {"ok": True}
