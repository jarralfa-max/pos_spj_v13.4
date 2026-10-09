"""Dar o quitar permisos a un rol — la única ruta (Configuración → Usuarios y
Roles → Permisos).

Antes este archivo envolvía un `module_access_service` que se borró con
`core/`: el caso de uso existía y nunca se pudo ejecutar, y no había forma de
cambiar los permisos de un rol desde la aplicación.

El caso de uso revalida TODO, aunque la pantalla ya lo filtre (§57):
1. Quien actúa tiene `CONFIGURACION.rol.permisos`.
2. Sólo se otorgan permisos del catálogo canónico.
3. Sin escalamiento: nadie otorga un permiso que no tiene (salvo el dueño de
   la instalación y los roles administradores).
4. Un rol administrador (acceso total por nombre) no se edita.
5. Al dueño de la instalación (`system_owner`) no se le quita nada.
6. Nadie se quita, en su propio rol, lo que necesita para volver a esta
   pantalla (entrar a Configuración, ver roles, administrar permisos).
Cada cambio queda auditado con el antes y el después, en la misma transacción.
"""

from __future__ import annotations

import json

from backend.application.commands.settings_commands import SaveRolePermissionsCommand
from backend.application.configuracion.permissions import ConfiguracionPermissions
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.security.permission_query_service import (
    GLOBAL_WILDCARD,
    PermissionQueryService,
)
from backend.application.security.role_permission_matrix import catalog_codes, role_mode
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    ConfigurationPermissionDeniedError,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.security.role_permission_repository import (
    SqliteRolePermissionRepository,
)
from backend.infrastructure.db.repositories.settings.configuracion_security_repositories import (
    ConfiguracionAuditLogRepository,
)
from backend.security.permissions.codes import normalize_permission, permission_code

#: Lo que un usuario no puede quitarse en su propio rol: perderlo lo dejaría
#: sin forma de volver a esta pantalla para deshacerlo.
SELF_LOCKOUT_CODES = frozenset({
    ConfiguracionPermissions.GENERAL_VIEW, ConfiguracionPermissions.USUARIOS_VIEW,
    ConfiguracionPermissions.ROLES_VIEW, ConfiguracionPermissions.ROLES_PERMISOS,
})


class SaveRolePermissionsUseCase(BaseUseCase[SaveRolePermissionsCommand]):
    name = "SaveRolePermissionsUseCase"

    def __init__(self, connection, authorization) -> None:
        if authorization is None:
            raise ValueError("SaveRolePermissionsUseCase requiere una política de autorización")
        self._conn = connection
        self._auth = authorization
        self._roles = SqliteRolePermissionRepository(connection)
        self._actor_permissions = PermissionQueryService(SqlitePermissionRepository(connection))
        self._audit = ConfiguracionAuditLogRepository(connection)

    def execute(self, command: SaveRolePermissionsCommand) -> UseCaseResult:
        command.validate_context()
        actor = str(command.user_id or "")
        self._auth.require(actor, ConfiguracionPermissions.ROLES_PERMISOS)

        role = self._roles.role(command.role_id)
        if role is None:
            raise ConfigurationInvalidValueError("El rol ya no existe.")
        role_id, role_name = role
        mode = role_mode(role_name)
        if mode == "FULL_ACCESS":
            raise ConfigurationInvalidValueError(
                f"«{role_name}» es un rol administrador con acceso total; no se edita.")

        wanted = self._requested(command)
        current = self._roles.granted(role_id)
        grant = sorted(c for c, allowed in wanted.items() if allowed and c not in current)
        revoke = sorted(c for c, allowed in wanted.items() if not allowed and c in current)
        if not grant and not revoke:
            return UseCaseResult(success=True, operation_id=command.operation_id,
                                 entity_id=role_id, message="Sin cambios.",
                                 data={"granted": (), "revoked": ()})

        if revoke and mode == "GRANT_ONLY":
            raise ConfigurationInvalidValueError(
                "Al dueño de la instalación no se le pueden quitar permisos.")
        self._guard_escalation(actor, grant)
        self._guard_self_lockout(actor, role_name, revoke)

        try:
            for code in grant:
                self._roles.grant(role_id, code)
            for code in revoke:
                self._roles.revoke(role_id, code)
            self._audit.record(
                entity_type="role_permissions", entity_id=role_id, action="ACTUALIZAR_PERMISOS",
                user_id=actor, operation_id=command.operation_id,
                before_json=json.dumps({"rol": role_name, "otorgados": revoke}, ensure_ascii=False),
                after_json=json.dumps({"rol": role_name, "otorgados": grant}, ensure_ascii=False),
                reason=f"{len(grant)} otorgados, {len(revoke)} retirados",
                branch_id=command.branch_id or None)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return UseCaseResult(
            success=True, operation_id=command.operation_id, entity_id=role_id,
            message=f"{len(grant)} permisos otorgados y {len(revoke)} retirados.",
            data={"granted": tuple(grant), "revoked": tuple(revoke)})

    # ── guardas ─────────────────────────────────────────────────────────
    @staticmethod
    def _requested(command: SaveRolePermissionsCommand) -> dict[str, bool]:
        validos = catalog_codes()
        salida = {}
        for item in command.permissions:
            code = permission_code(str(item["module"]), str(item["action"]))
            if code not in validos:
                raise ConfigurationInvalidValueError(f"{code} no es un permiso del catálogo.")
            salida[code] = bool(item.get("allowed", False))
        return salida

    def _guard_escalation(self, actor: str, grant: list[str]) -> None:
        # El dueño de la instalación es la autoridad máxima: sus permisos están
        # sembrados uno a uno y a los módulos nuevos les faltan, así que sin esta
        # excepción no podría otorgar (ni otorgarse) lo que aún no tiene.
        rol_actor = SqlitePermissionRepository(self._conn).user_role_name(actor) or ""
        if role_mode(rol_actor) == "GRANT_ONLY":
            return
        mios = self._actor_permissions.permission_codes_for_user(actor)
        if GLOBAL_WILDCARD in mios:
            return
        ajenos = [c for c in grant if normalize_permission(c) not in mios]
        if ajenos:
            raise ConfigurationPermissionDeniedError(
                "No puedes otorgar permisos que tú no tienes: " + ", ".join(ajenos[:5])
                + ("…" if len(ajenos) > 5 else ""))

    def _guard_self_lockout(self, actor: str, role_name: str, revoke: list[str]) -> None:
        propio = (SqlitePermissionRepository(self._conn).user_role_name(actor) or "").strip().lower()
        if propio != role_name.strip().lower():
            return
        criticos = sorted(set(revoke) & {permission_code(*c.split(".", 1))
                                         for c in SELF_LOCKOUT_CODES})
        if criticos:
            raise ConfigurationInvalidValueError(
                "No puedes quitarte, en tu propio rol, lo que necesitas para administrar "
                "permisos: " + ", ".join(criticos))
