"""Excepciones de permiso de UN usuario — la única ruta (Configuración →
Usuarios y Roles → Usuarios → Permisos).

Revalida todo aunque la pantalla ya lo filtre (§57):
1. Quien actúa tiene `CONFIGURACION.usuario.permisos`.
2. Nadie edita sus propios permisos (concederse algo es escalarse).
3. Sólo permisos del catálogo canónico.
4. Sin escalamiento: nadie concede lo que no tiene (salvo dueño y administradores).
5. Un usuario con rol administrador no lleva excepciones: tiene acceso total.
6. Al dueño de la instalación no se le niega nada.
Cada cambio queda auditado con el antes y el después, en la misma transacción.
Rige en el siguiente inicio de sesión del usuario.
"""

from __future__ import annotations

import json

from backend.application.commands.settings_commands import SaveUserPermissionsCommand
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.security.permission_query_service import (
    GLOBAL_WILDCARD,
    PermissionQueryService,
)
from backend.application.security.role_permission_matrix import catalog_codes, role_mode
from backend.application.security.user_permission_matrix import DENY, GRANT, INHERIT
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    ConfigurationPermissionDeniedError,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.security.user_permission_repository import (
    SqliteUserPermissionRepository,
)
from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
    ConfiguracionAuditLogRepository,
)
from backend.security.permissions.codes import normalize_permission, permission_code


class SaveUserPermissionsUseCase(BaseUseCase[SaveUserPermissionsCommand]):
    name = "SaveUserPermissionsUseCase"

    def __init__(self, connection, authorization) -> None:
        if authorization is None:
            raise ValueError("SaveUserPermissionsUseCase requiere una política de autorización")
        self._conn = connection
        self._auth = authorization
        self._users = SqliteUserPermissionRepository(connection)
        self._permissions = SqlitePermissionRepository(connection)
        self._audit = ConfiguracionAuditLogRepository(connection)

    def execute(self, command: SaveUserPermissionsCommand) -> UseCaseResult:
        command.validate_context()
        actor = str(command.user_id or "")
        self._auth.require(actor, ConfiguracionPermissions.USUARIOS_PERMISOS)
        if actor == str(command.target_user_id):
            raise ConfigurationPermissionDeniedError("Nadie puede editar sus propios permisos.")

        target = self._users.user(command.target_user_id)
        if target is None:
            raise ConfigurationInvalidValueError("El usuario ya no existe.")
        user_id, user_name, role_name = target
        mode = role_mode(role_name)
        if mode == "FULL_ACCESS":
            raise ConfigurationInvalidValueError(
                f"{user_name} tiene un rol administrador con acceso total; no lleva excepciones.")

        current = self._users.overrides(user_id)
        changes = {
            code: state for code, state in self._requested(command).items()
            if state != _state_of(current, code)}
        if not changes:
            return UseCaseResult(success=True, operation_id=command.operation_id,
                                 entity_id=user_id, message="Sin cambios.", data={"changes": {}})
        if mode == "GRANT_ONLY" and DENY in changes.values():
            raise ConfigurationInvalidValueError(
                "Al dueño de la instalación no se le puede negar ningún permiso.")
        self._guard_escalation(actor, [c for c, s in changes.items() if s == GRANT])

        antes = {c: _state_of(current, c) for c in changes}
        try:
            for code, state in changes.items():
                if state == INHERIT:
                    self._users.clear(user_id, code)
                else:
                    self._users.set(user_id, code, state == GRANT)
            self._audit.record(
                entity_type="user_permissions", entity_id=user_id, action="ACTUALIZAR_PERMISOS",
                user_id=actor, operation_id=command.operation_id,
                before_json=json.dumps({"usuario": user_name, "excepciones": antes},
                                       ensure_ascii=False),
                after_json=json.dumps({"usuario": user_name, "excepciones": changes},
                                      ensure_ascii=False),
                reason=f"{len(changes)} excepciones cambiadas", branch_id=command.branch_id or None)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=user_id,
            message=f"{len(changes)} permisos actualizados para {user_name}.",
            data={"changes": dict(changes)})

    @staticmethod
    def _requested(command: SaveUserPermissionsCommand) -> dict[str, str]:
        validos = catalog_codes()
        salida = {}
        for item in command.permissions:
            code = permission_code(str(item["module"]), str(item["action"]))
            state = str(item.get("state", INHERIT)).upper()
            if code not in validos:
                raise ConfigurationInvalidValueError(f"{code} no es un permiso del catálogo.")
            if state not in (INHERIT, GRANT, DENY):
                raise ConfigurationInvalidValueError(f"Estado de permiso inválido: {state}")
            salida[code] = state
        return salida

    def _guard_escalation(self, actor: str, grant: list[str]) -> None:
        if not grant:
            return
        if role_mode(self._permissions.user_role_name(actor) or "") == "GRANT_ONLY":
            return
        mios = PermissionQueryService(self._permissions).permission_codes_for_user(actor)
        if GLOBAL_WILDCARD in mios:
            return
        ajenos = [c for c in grant if normalize_permission(c) not in mios]
        if ajenos:
            raise ConfigurationPermissionDeniedError(
                "No puedes conceder permisos que tú no tienes: " + ", ".join(ajenos[:5])
                + ("…" if len(ajenos) > 5 else ""))


def _state_of(overrides: dict, code: str) -> str:
    if code not in overrides:
        return INHERIT
    return GRANT if overrides[code] else DENY
