"""Servicios de aplicación de Configuración → Seguridad y Empresa.

Reemplazan las clases homónimas de `core/services/configuration_settings_service.py`
(borrado). Los nombres de clase y de método se conservan porque los consumidores
son código canónico vivo que no tiene por qué cambiar: `SaveUserUseCase`,
`SetUserActiveUseCase`, `SaveRoleUseCase`, `SetInstallationBranchUseCase` y
`ConfiguracionWorkspaceQueryService`.

Lo que sí cambia es de qué dependen: antes recibían `ConfigRepository`, una
clase de 828 líneas que hacía de todo —ajustes, sucursales, happy hour, cierres
mensuales, usuarios, roles, permisos, auditoría— desde una carpeta fuera de las
raíces válidas (§1). Ahora cada servicio recibe el repositorio acotado que
necesita.

TRES CLASES, NO CUATRO. La cuarta del módulo original, `PermissionQueryService`,
no se reconstruye aquí: mezclaba dos cosas distintas. Resolver los permisos de
un usuario ya vive en `backend/application/security/permission_query_service.py`
(PASS 2), y leer el rastro de auditoría es
`SqliteAuditLogRepository`. Mantener el nombre habría dejado dos clases
distintas llamadas igual haciendo cosas distintas.
"""

from __future__ import annotations


class UserManagementService:
    """Altas, bajas y edición de cuentas de usuario.

    `audit_log_repository` es opcional para que las lecturas puedan construirse
    sin él, pero cualquier ESCRITURA sin auditoría es una decisión, no un
    descuido: crear o desactivar una cuenta es exactamente lo que la regla 12
    de CLAUDE.md exige dejar registrado.
    """

    def __init__(self, user_directory_repository, audit_log_repository=None) -> None:
        self._repository = user_directory_repository
        self._audit = audit_log_repository

    def list_users(self) -> list[tuple]:
        return self._repository.list_users()

    def get_user_form_data(self, user_id: str) -> tuple | None:
        return self._repository.get_user_form_data(user_id)

    def save_user(
        self, *, user_id: str | None, username: str, name: str, email: str,
        role: str, branch_id: str, active: bool, employee_id: int | None,
        password_hash: str | None, operation_id: str = "", actor: str = "",
    ) -> str:
        persisted_id = self._repository.save_user(
            user_id=user_id, username=username, name=name, email=email, role=role,
            branch_id=branch_id, active=active, employee_id=employee_id,
            password_hash=password_hash,
        )
        self._record(
            action="usuario.actualizar" if user_id else "usuario.crear",
            entity_id=persisted_id, operation_id=operation_id, actor=actor,
            details=f"usuario={username} rol={role}",
        )
        return persisted_id

    def set_user_active(
        self, user_id: str, active: bool, *, operation_id: str = "", actor: str = "",
    ) -> None:
        self._repository.set_user_active(user_id, active)
        self._record(
            action="usuario.activar" if active else "usuario.desactivar",
            entity_id=user_id, operation_id=operation_id, actor=actor,
        )

    def _record(self, *, action: str, entity_id: str, operation_id: str,
                actor: str, details: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record(
            action=action, entity="usuario", entity_id=entity_id,
            actor=actor, operation_id=operation_id, details=details,
        )


class RoleManagementService:
    """Roles y los selectores que alimentan el formulario de usuario.

    Los selectores de sucursal y empleado viven aquí, y no en un servicio
    propio, porque su única razón de existir es rellenar los desplegables del
    alta de usuario — que es lo que administra este servicio.
    """

    def __init__(self, user_directory_repository, audit_log_repository=None) -> None:
        self._repository = user_directory_repository
        self._audit = audit_log_repository

    def list_roles(self) -> list[tuple]:
        return self._repository.list_roles()

    def role_names(self) -> list[str]:
        return self._repository.role_names()

    def save_role(
        self, *, role_id: str | None, name: str, description: str,
        operation_id: str = "", actor: str = "",
    ) -> str:
        persisted_id = self._repository.save_role(
            role_id=role_id, name=name, description=description)
        if self._audit is not None:
            self._audit.record(
                action="rol.actualizar" if role_id else "rol.crear", entity="rol",
                entity_id=persisted_id, actor=actor, operation_id=operation_id,
                details=f"nombre={name}",
            )
        return persisted_id

    def active_branches_for_selector(self) -> list[tuple[str, str]]:
        return self._repository.active_branches_for_selector()

    def active_employees_for_selector(self) -> list[tuple[int, str]]:
        return self._repository.active_employees_for_selector()


class CompanyProfileService:
    """Qué sucursal es esta instalación."""

    def __init__(self, installation_branch_repository) -> None:
        self._repository = installation_branch_repository

    def get_installation_branch(self) -> tuple[str, str] | None:
        return self._repository.get()

    def set_installation_branch(self, branch_id: str) -> tuple[str, str]:
        return self._repository.set(branch_id)
