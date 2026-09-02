"""Declarative internal sidebar for the one global Configuración entry —
UI/UX phase. Mirrors
`frontend/desktop/modules/transfers/navigation/transfers_sidebar.py`'s
shape. Presentation data only — no Qt, SQL, repository, or permission
decision logic.

Governs the 4 bounded contexts SET-0's own scope explicitly named as
"un único punto de entrada de navegación Configuración"
(`docs/refactor/settings_refactor_execution_plan.md` §"Alcance") —
settings (general/integraciones/feature_flags/apariencia/notificaciones/
offline all fold into it), device_management, document_output,
customer_display. Notifications (SET-20) and Offline (SET-23) postdate
that original scope text but have no dedicated permission group either,
so they fold in the same way integrations/feature-flags/appearance
already do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.configuracion.permissions import ConfiguracionPermissions


@dataclass(frozen=True, slots=True)
class ConfiguracionNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None


CONFIGURACION_NAV: tuple[ConfiguracionNavEntry, ...] = (
    ConfiguracionNavEntry(
        "config_empresa", "Empresa y sucursales", "company", ConfiguracionPermissions.EMPRESA_VIEW,
        "Perfil de la empresa y gobierno de sucursales.",
    ),
    ConfiguracionNavEntry(
        "config_general", "General", "dashboard", ConfiguracionPermissions.GENERAL_VIEW,
        "Estaciones de trabajo registradas.",
    ),
    ConfiguracionNavEntry(
        "config_dispositivos", "Dispositivos", "device", ConfiguracionPermissions.DISPOSITIVOS_VIEW,
        "Impresoras, básculas, cajones y terminales.",
    ),
    ConfiguracionNavEntry(
        "config_documentos", "Documentos", "document", ConfiguracionPermissions.DOCUMENTOS_VIEW,
        "Plantillas de tickets, etiquetas y numeración.",
    ),
    ConfiguracionNavEntry(
        "config_pantalla_cliente", "Pantalla del cliente", "display",
        ConfiguracionPermissions.PANTALLA_CLIENTE_VIEW, "Displays, contenido y publicidad.",
    ),
    ConfiguracionNavEntry(
        "config_integraciones", "Integraciones", "integration", ConfiguracionPermissions.INTEGRACIONES_VIEW,
        "WhatsApp, pagos, mapas y webhooks.",
    ),
    ConfiguracionNavEntry(
        "config_feature_flags", "Feature Flags", "flag", ConfiguracionPermissions.FEATURE_FLAGS_VIEW,
        "Banderas, reglas de alcance y solicitudes pendientes.", "pending_flag_requests",
    ),
    ConfiguracionNavEntry(
        "config_apariencia", "Apariencia", "theme", ConfiguracionPermissions.APARIENCIA_VIEW,
        "Temas, tokens de diseño y densidad.",
    ),
    ConfiguracionNavEntry(
        "config_notificaciones", "Notificaciones", "notifications",
        ConfiguracionPermissions.NOTIFICACIONES_VIEW, "Cuentas, plantillas y ruteo de notificaciones.",
    ),
    ConfiguracionNavEntry(
        "config_offline", "Offline", "offline", ConfiguracionPermissions.OFFLINE_VIEW,
        "Políticas de caché y expiración por tipo de entidad.",
    ),
    ConfiguracionNavEntry(
        "config_usuarios_roles", "Usuarios y Roles", "users", ConfiguracionPermissions.USUARIOS_VIEW,
        "Usuarios, roles y auditoría del sistema.",
    ),
)


def visible_entries(
    has_permission: Callable[[str], bool], badges: Mapping[str, int] | None = None,
) -> tuple[tuple[ConfiguracionNavEntry, int | None], ...]:
    """Return only permitted entries and server-calculated optional badge counts."""
    badges = badges or {}
    return tuple(
        (entry, badges.get(entry.badge_key) if entry.badge_key else None)
        for entry in CONFIGURACION_NAV if has_permission(entry.permission)
    )
