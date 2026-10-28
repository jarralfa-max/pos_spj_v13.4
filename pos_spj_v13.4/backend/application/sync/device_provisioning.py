"""Aprovisionamiento de equipos en el servidor central (auditoría enterprise,
Fase 4; decisión D3).

Flujo (prompt §6):

1. Un administrador autorizado crea una INVITACIÓN: sucursal o sitio, tipo de
   estación y capacidades. Se genera un código aleatorio de un solo uso y vida
   corta (30 min por omisión, máximo 24 h). El servidor guarda sólo su huella.
2. En el equipo, el asistente pide vincularse: el equipo genera su par Ed25519
   localmente y manda el código con su llave PÚBLICA.
3. El servidor valida código, estado, vigencia y alcance, lo consume en la misma
   transacción (dos equipos con el mismo código: gana uno, el otro recibe
   «código ya usado») y registra la estación con identidad UUIDv7.
4. La credencial que queda es la propia llave del equipo: cada solicitud va
   firmada. El servidor NUNCA entrega credenciales de PostgreSQL ni secretos
   compartidos.

Administración (la piden estaciones de ADMINISTRACIÓN, firmando con su llave; el
permiso del usuario lo verificó la aplicación de esa estación —los usuarios aún
no están en el central, Fase 6—): invitar, suspender, reactivar, dar de baja,
reasignar de sucursal, invitar a reemplazo o a recuperación, ver equipos e
historial. Todo queda en `central_device_events`.

Reglas: ninguna identidad se toma sin invitación de reemplazo o recuperación; una
estación dada de baja no vuelve; una estación de administración no se da de baja
a sí misma.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.shared.security.device_signature import (
    ALGORITHM,
    DeviceSignatureError,
    NonceCache,
    validate_public_key,
    verify_request,
)

DEFAULT_TTL_MINUTES = 30
MAX_TTL_MINUTES = 24 * 60
#: `credential_hash` de un equipo vinculado por invitación: ninguna huella SHA-256
#: lo iguala, así que el secreto del Slice 4 no sirve para él.
NO_SECRET = "!"
WORKSTATION_TYPES = ("POS", "BACK_OFFICE", "WAREHOUSE", "PRODUCTION", "LOGISTICS",
                     "KIOSK", "ADMIN")
INVITATION_KINDS = ("NEW", "REPLACEMENT", "RECOVERY")


class ProvisioningError(ValueError):
    """La operación no procede (código inválido, vencido, usado, alcance…)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeviceNotAuthorizedError(PermissionError):
    """Firma inválida, estación inexistente o sin permiso para la operación."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeviceRegistryRepository(Protocol):
    def get_station(self, station_id: str) -> Mapping[str, Any] | None: ...
    def list_stations(self) -> list[Mapping[str, Any]]: ...
    def insert_invitation(self, row: Mapping[str, Any]) -> None: ...
    def invitation_by_hash(self, token_hash: str) -> Mapping[str, Any] | None: ...
    def consume_invitation(self, invitation_id: str, *, station_id: str,
                           now: datetime) -> bool: ...
    def revoke_invitation(self, invitation_id: str) -> bool: ...
    def list_invitations(self, *, now: datetime) -> list[Mapping[str, Any]]: ...
    def register_device_station(self, *, station_id: str, branch_id: str, display_name: str,
                                public_key: str, workstation_type: str,
                                capabilities: Sequence[str], is_admin: bool,
                                invitation_id: str) -> None: ...
    def rotate_station_key(self, station_id: str, *, public_key: str,
                           invitation_id: str) -> None: ...
    def set_station_status(self, station_id: str, status: str, *, now: datetime) -> bool: ...
    def mark_replaced(self, station_id: str, *, replaced_by: str, now: datetime) -> None: ...
    def reassign_station(self, station_id: str, *, branch_id: str) -> None: ...
    def report_heartbeat(self, station_id: str, *, app_version: str | None,
                         pending_events: int | None, last_sync_at: datetime | None,
                         now: datetime) -> None: ...
    def add_device_event(self, *, station_id: str | None, invitation_id: str | None,
                         event: str, actor_station: str | None, actor_user: str | None,
                         detail: Mapping[str, Any], now: datetime) -> None: ...
    def device_events(self, station_id: str) -> list[Mapping[str, Any]]: ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class IssuedInvitation:
    invitation_id: str
    code: str            # se muestra UNA vez
    expires_at: datetime
    kind: str


@dataclass(frozen=True)
class Enrollment:
    station_id: str
    branch_id: str
    workstation_type: str
    capabilities: tuple[str, ...]
    is_admin_station: bool
    #: Última secuencia que el central ya tiene de esta identidad (recuperación):
    #: la estación continúa desde aquí y no reutiliza números.
    resume_sequence: int
    replaced_station_id: str | None
    server_time: datetime

    def to_dict(self) -> dict:
        return {"station_id": self.station_id, "branch_id": self.branch_id,
                "workstation_type": self.workstation_type,
                "capabilities": list(self.capabilities),
                "is_admin_station": self.is_admin_station,
                "resume_sequence": self.resume_sequence,
                "replaced_station_id": self.replaced_station_id,
                "server_time": self.server_time.isoformat()}


def invitation_hash(code: str) -> str:
    normalizado = "".join(c for c in str(code or "").upper() if c.isalnum())
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def _new_code() -> str:
    """`SPJ-XXXX-XXXX-XXXX-XXXX-XXXX`: 100 bits en base32 legible."""
    crudo = base64.b32encode(secrets.token_bytes(15)).decode("ascii").rstrip("=")[:20]
    return "SPJ-" + "-".join(crudo[i:i + 4] for i in range(0, 20, 4))


class DeviceProvisioningService:
    def __init__(self, repository: DeviceRegistryRepository, *,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 nonces: NonceCache | None = None) -> None:
        self._repo = repository
        self._clock = clock
        self._nonces = nonces

    # ── autenticación de un equipo ──────────────────────────────────────
    def authenticate_signed(self, *, method: str, path: str, headers: Mapping[str, str],
                            body: bytes, require_active: bool = True) -> Mapping[str, Any]:
        estacion_id = headers.get("X-SPJ-Station-Id") or headers.get("x-spj-station-id")
        try:
            validate_uuidv7(str(estacion_id or ""))
        except Exception:
            raise DeviceNotAuthorizedError("BAD_SIGNATURE", "Firma de equipo inválida") from None
        estacion = self._repo.get_station(str(estacion_id))
        if estacion is None or not estacion.get("public_key"):
            raise DeviceNotAuthorizedError("BAD_SIGNATURE", "Firma de equipo inválida")
        try:
            verify_request(estacion["public_key"], method=method, path=path, headers=headers,
                           body=body, nonces=self._nonces,
                           now=self._clock().timestamp())
        except DeviceSignatureError:
            raise DeviceNotAuthorizedError("BAD_SIGNATURE", "Firma de equipo inválida") from None
        if require_active and estacion["status"] != "ACTIVE":
            codigo = "DEVICE_REVOKED" if estacion["status"] == "RETIRED" else "DEVICE_SUSPENDED"
            raise DeviceNotAuthorizedError(codigo, f"El equipo está {estacion['status']}")
        return estacion

    def _admin(self, actor_station: Mapping[str, Any]) -> None:
        if not actor_station.get("is_admin_station"):
            raise DeviceNotAuthorizedError("NOT_ADMIN_STATION",
                                           "Esta estación no administra equipos")

    # ── invitaciones ────────────────────────────────────────────────────
    def create_invitation(self, *, branch_id: str, workstation_type: str,
                          capabilities: Sequence[str] = (), kind: str = "NEW",
                          target_station_id: str | None = None, display_name: str = "",
                          ttl_minutes: int = DEFAULT_TTL_MINUTES, grants_admin: bool = False,
                          actor_station: Mapping[str, Any] | None = None,
                          actor_user: str | None = None) -> IssuedInvitation:
        """`actor_station=None` sólo desde el servidor (script del operador)."""
        if actor_station is not None:
            self._admin(actor_station)
        validate_uuidv7(branch_id)
        if kind not in INVITATION_KINDS:
            raise ProvisioningError("BAD_KIND", f"Tipo de invitación desconocido: {kind}")
        if workstation_type not in WORKSTATION_TYPES:
            raise ProvisioningError("BAD_TYPE", f"Tipo de estación desconocido: {workstation_type}")
        if not 1 <= int(ttl_minutes) <= MAX_TTL_MINUTES:
            raise ProvisioningError("BAD_TTL", "La invitación vive de 1 minuto a 24 horas")
        if kind == "NEW":
            target_station_id = None
        else:
            objetivo = self._repo.get_station(str(target_station_id or ""))
            if objetivo is None:
                raise ProvisioningError("UNKNOWN_STATION", "La estación a reemplazar o "
                                        "recuperar no existe")
            # Equipo robado: primero se da de baja y después se invita al reemplazo.
            # Lo que no se permite es recuperar una baja ni reemplazar dos veces.
            if objetivo.get("replaced_by"):
                raise ProvisioningError("ALREADY_REPLACED", "Esa estación ya fue reemplazada")
            if objetivo["status"] == "RETIRED" and kind == "RECOVERY":
                raise ProvisioningError("STATION_RETIRED", "Una estación dada de baja no se "
                                        "recupera; invite a un reemplazo")
            branch_id = str(objetivo["branch_id"])
        ahora = self._clock()
        codigo = _new_code()
        invitacion = {
            "id": new_uuid(), "token_hash": invitation_hash(codigo), "kind": kind,
            "branch_id": branch_id, "workstation_type": workstation_type,
            "capabilities": sorted(set(capabilities)), "display_name": display_name.strip(),
            "grants_admin": bool(grants_admin), "target_station_id": target_station_id,
            "created_by_station": (actor_station or {}).get("id"),
            "created_by_user": actor_user, "created_at": ahora,
            "expires_at": ahora + timedelta(minutes=int(ttl_minutes))}
        self._repo.insert_invitation(invitacion)
        self._repo.add_device_event(
            station_id=target_station_id, invitation_id=invitacion["id"],
            event=f"INVITATION_CREATED_{kind}",
            actor_station=invitacion["created_by_station"], actor_user=actor_user,
            detail={"branch_id": branch_id, "workstation_type": workstation_type,
                    "expires_at": invitacion["expires_at"].isoformat()}, now=ahora)
        self._repo.commit()
        return IssuedInvitation(invitacion["id"], codigo, invitacion["expires_at"], kind)

    def revoke_invitation(self, invitation_id: str, *, actor_station: Mapping[str, Any],
                          actor_user: str | None = None) -> None:
        self._admin(actor_station)
        if not self._repo.revoke_invitation(invitation_id):
            raise ProvisioningError("NOT_PENDING", "La invitación ya no está pendiente")
        self._repo.add_device_event(station_id=None, invitation_id=invitation_id,
                                    event="INVITATION_REVOKED", actor_station=actor_station["id"],
                                    actor_user=actor_user, detail={}, now=self._clock())
        self._repo.commit()

    # ── vinculación ─────────────────────────────────────────────────────
    def enroll(self, *, code: str, public_key: str, app_version: str = "",
               hostname: str = "", expected_branch_id: str | None = None) -> Enrollment:
        """El hostname es sólo descriptivo: no autentica nada. `expected_branch_id`:
        el sitio anclado a la estación; si la invitación es para otro, se rechaza
        ANTES de consumir el código (sigue sirviendo en el equipo correcto)."""
        try:
            llave = validate_public_key(public_key)
        except DeviceSignatureError as exc:
            raise ProvisioningError("BAD_KEY", str(exc)) from None
        inv = self._repo.invitation_by_hash(invitation_hash(code))
        ahora = self._clock()
        if inv is None:
            raise ProvisioningError("INVALID_CODE", "Código de invitación inválido")
        if inv["status"] == "CONSUMED":
            raise ProvisioningError("CODE_USED", "Ese código ya se usó")
        if inv["status"] == "REVOKED":
            raise ProvisioningError("CODE_REVOKED", "Ese código fue revocado")
        if inv["expires_at"] <= ahora:
            raise ProvisioningError("CODE_EXPIRED", "El código venció; pida otro")
        kind = inv["kind"]
        anterior = None
        resume = 0
        if kind == "RECOVERY":
            objetivo = self._repo.get_station(str(inv["target_station_id"]))
            if objetivo is None or objetivo["status"] == "RETIRED":
                raise ProvisioningError("STATION_RETIRED", "La estación ya no se puede recuperar")
            estacion_id = str(objetivo["id"])
            resume = int(objetivo.get("last_sequence") or 0)
        else:
            if kind == "REPLACEMENT":
                previa = self._repo.get_station(str(inv["target_station_id"]))
                if previa is None or previa.get("replaced_by"):
                    raise ProvisioningError("ALREADY_REPLACED", "Esa estación ya fue reemplazada")
            estacion_id = new_uuid()
        destino = str(objetivo["branch_id"]) if kind == "RECOVERY" else str(inv["branch_id"])
        if expected_branch_id and str(expected_branch_id) != destino:
            raise ProvisioningError("BRANCH_MISMATCH", "La invitación es para otra sucursal que "
                                    "la de este equipo")
        # Consumir primero: si dos equipos usan el mismo código a la vez, sólo uno
        # gana (UPDATE … WHERE status='PENDING').
        if not self._repo.consume_invitation(str(inv["id"]), station_id=estacion_id, now=ahora):
            raise ProvisioningError("CODE_USED", "Ese código ya se usó")
        detalle = {"app_version": app_version, "hostname": hostname, "kind": kind}
        if kind == "RECOVERY":
            self._repo.rotate_station_key(estacion_id, public_key=llave,
                                          invitation_id=str(inv["id"]))
            if objetivo["status"] == "SUSPENDED":
                self._repo.set_station_status(estacion_id, "ACTIVE", now=ahora)
            evento = "DEVICE_RECOVERED"
        else:
            self._repo.register_device_station(
                station_id=estacion_id, branch_id=str(inv["branch_id"]),
                display_name=inv.get("display_name") or hostname, public_key=llave,
                workstation_type=inv["workstation_type"],
                capabilities=list(inv.get("capabilities") or ()),
                is_admin=bool(inv.get("grants_admin")), invitation_id=str(inv["id"]))
            evento = "DEVICE_ENROLLED"
            if kind == "REPLACEMENT":
                anterior = str(inv["target_station_id"])
                self._repo.mark_replaced(anterior, replaced_by=estacion_id, now=ahora)
                self._repo.add_device_event(
                    station_id=anterior, invitation_id=str(inv["id"]), event="DEVICE_REPLACED",
                    actor_station=inv.get("created_by_station"),
                    actor_user=inv.get("created_by_user"),
                    detail={"replaced_by": estacion_id}, now=ahora)
                detalle["replaces"] = anterior
        self._repo.add_device_event(station_id=estacion_id, invitation_id=str(inv["id"]),
                                    event=evento, actor_station=inv.get("created_by_station"),
                                    actor_user=inv.get("created_by_user"), detail=detalle,
                                    now=ahora)
        self._repo.commit()
        estacion = self._repo.get_station(estacion_id) or {}
        return Enrollment(
            station_id=estacion_id, branch_id=str(estacion.get("branch_id") or inv["branch_id"]),
            workstation_type=str(estacion.get("workstation_type") or inv["workstation_type"]),
            capabilities=tuple(estacion.get("capabilities") or inv.get("capabilities") or ()),
            is_admin_station=bool(estacion.get("is_admin_station")),
            resume_sequence=resume, replaced_station_id=anterior, server_time=ahora)

    # ── el equipo informa ───────────────────────────────────────────────
    def heartbeat(self, station: Mapping[str, Any], *, app_version: str | None,
                  pending_events: int | None, last_sync_at: datetime | None) -> dict:
        self._repo.report_heartbeat(str(station["id"]), app_version=app_version,
                                    pending_events=pending_events, last_sync_at=last_sync_at,
                                    now=self._clock())
        self._repo.commit()
        return self.status_of(station)

    @staticmethod
    def status_of(station: Mapping[str, Any]) -> dict:
        return {"station_id": str(station["id"]), "status": station["status"],
                "branch_id": str(station["branch_id"]),
                "workstation_type": station.get("workstation_type"),
                "capabilities": list(station.get("capabilities") or ()),
                "is_admin_station": bool(station.get("is_admin_station")),
                "replaced_by": station.get("replaced_by")}

    # ── administración ──────────────────────────────────────────────────
    def list_devices(self, *, actor_station: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        self._admin(actor_station)
        return self._repo.list_stations()

    def list_invitations(self, *, actor_station: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        self._admin(actor_station)
        return self._repo.list_invitations(now=self._clock())

    def history(self, station_id: str, *,
                actor_station: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        self._admin(actor_station)
        return self._repo.device_events(station_id)

    def change_status(self, station_id: str, action: str, *, reason: str,
                      actor_station: Mapping[str, Any], actor_user: str | None = None) -> None:
        self._admin(actor_station)
        destino = {"suspend": "SUSPENDED", "reactivate": "ACTIVE", "revoke": "RETIRED"}.get(action)
        if destino is None:
            raise ProvisioningError("BAD_ACTION", f"Acción desconocida: {action}")
        if not str(reason or "").strip():
            raise ProvisioningError("REASON_REQUIRED", "Indique el motivo")
        estacion = self._repo.get_station(station_id)
        if estacion is None:
            raise ProvisioningError("UNKNOWN_STATION", "La estación no existe")
        if estacion["status"] == "RETIRED":
            raise ProvisioningError("STATION_RETIRED", "La estación ya está dada de baja")
        if str(station_id) == str(actor_station["id"]) and destino != "ACTIVE":
            raise ProvisioningError("SELF_LOCKOUT", "Una estación no se suspende ni se da de "
                                    "baja a sí misma")
        ahora = self._clock()
        self._repo.set_station_status(station_id, destino, now=ahora)
        self._repo.add_device_event(
            station_id=station_id, invitation_id=None, event=f"DEVICE_{destino}",
            actor_station=actor_station["id"], actor_user=actor_user,
            detail={"reason": reason.strip(), "from": estacion["status"]}, now=ahora)
        self._repo.commit()

    def reassign(self, station_id: str, *, branch_id: str, reason: str,
                 actor_station: Mapping[str, Any], actor_user: str | None = None) -> None:
        """Mueve un equipo a otro sitio. Su historial (eventos ya recibidos con la
        sucursal anterior) no cambia: cada hecho conserva su `branch_id`."""
        self._admin(actor_station)
        validate_uuidv7(branch_id)
        if not str(reason or "").strip():
            raise ProvisioningError("REASON_REQUIRED", "Indique el motivo")
        estacion = self._repo.get_station(station_id)
        if estacion is None or estacion["status"] == "RETIRED":
            raise ProvisioningError("UNKNOWN_STATION", "La estación no existe o está de baja")
        if str(estacion["branch_id"]) == str(branch_id):
            return
        ahora = self._clock()
        self._repo.reassign_station(station_id, branch_id=branch_id)
        self._repo.add_device_event(
            station_id=station_id, invitation_id=None, event="DEVICE_REASSIGNED",
            actor_station=actor_station["id"], actor_user=actor_user,
            detail={"from": str(estacion["branch_id"]), "to": branch_id,
                    "reason": reason.strip()}, now=ahora)
        self._repo.commit()


__all__ = ["ALGORITHM", "DEFAULT_TTL_MINUTES", "DeviceNotAuthorizedError",
           "DeviceProvisioningService", "DeviceRegistryRepository", "Enrollment",
           "INVITATION_KINDS", "IssuedInvitation", "MAX_TTL_MINUTES", "NO_SECRET",
           "ProvisioningError", "WORKSTATION_TYPES", "invitation_hash"]
