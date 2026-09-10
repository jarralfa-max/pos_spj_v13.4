"""Permission codes for the Configuración workspace — UI/UX phase.

Unlike most modules' `permissions.py` (flat `MODULE_ACTION` string
literals, e.g. `backend/application/transfers/permissions.py`),
Configuración governs 4 bounded contexts that already have a real,
shipped catalog (`core/security/permission_catalog.py`, `SET-1`):
`CONFIGURACION` (settings incl. integrations/feature-flags/appearance/
notifications/offline), `DISPOSITIVOS`, `DOCUMENTOS`, `PANTALLA_CLIENTE`.
This module references those existing codes via `permission_code()` —
never invents a new scheme.
"""

from __future__ import annotations

from backend.security.permissions.codes import permission_code


class ConfiguracionPermissions:
    GENERAL_VIEW = permission_code("CONFIGURACION", "ver")
    ESTACION_VIEW = permission_code("CONFIGURACION", "estacion.ver")
    ESTACION_CREAR = permission_code("CONFIGURACION", "estacion.crear")
    ESTACION_EDITAR = permission_code("CONFIGURACION", "estacion.editar")
    ESTACION_BLOQUEAR = permission_code("CONFIGURACION", "estacion.bloquear")
    ESTACION_RETIRAR = permission_code("CONFIGURACION", "estacion.retirar")
    EMPRESA_VIEW = permission_code("CONFIGURACION", "empresa.ver")
    EMPRESA_EDITAR = permission_code("CONFIGURACION", "empresa.editar")
    SUCURSAL_VIEW = permission_code("CONFIGURACION", "sucursal.ver")
    SUCURSAL_CREAR = permission_code("CONFIGURACION", "sucursal.crear")
    SUCURSAL_EDITAR = permission_code("CONFIGURACION", "sucursal.editar")
    DISPOSITIVOS_VIEW = permission_code("DISPOSITIVOS", "ver")
    DISPOSITIVOS_CREAR = permission_code("DISPOSITIVOS", "crear")
    DISPOSITIVOS_EDITAR = permission_code("DISPOSITIVOS", "editar")
    DISPOSITIVOS_ASIGNAR = permission_code("DISPOSITIVOS", "asignar")
    DISPOSITIVOS_DESHABILITAR = permission_code("DISPOSITIVOS", "deshabilitar")
    DISPOSITIVOS_RUTAS_GESTIONAR = permission_code("DISPOSITIVOS", "configuracion.gestionar")
    DOCUMENTOS_VIEW = permission_code("DOCUMENTOS", "plantilla.ver")
    DOCUMENTOS_PLANTILLA_CREAR = permission_code("DOCUMENTOS", "plantilla.crear")
    DOCUMENTOS_PLANTILLA_EDITAR = permission_code("DOCUMENTOS", "plantilla.editar")
    DOCUMENTOS_PLANTILLA_APROBAR = permission_code("DOCUMENTOS", "plantilla.aprobar")
    DOCUMENTOS_PLANTILLA_ACTIVAR = permission_code("DOCUMENTOS", "plantilla.activar")
    DOCUMENTOS_CAMPANA_VIEW = permission_code("DOCUMENTOS", "campana.ver")
    DOCUMENTOS_CAMPANA_CREAR = permission_code("DOCUMENTOS", "campana.crear")
    DOCUMENTOS_CAMPANA_EDITAR = permission_code("DOCUMENTOS", "campana.editar")
    DOCUMENTOS_CAMPANA_ACTIVAR = permission_code("DOCUMENTOS", "campana.activar")
    PANTALLA_CLIENTE_VIEW = permission_code("PANTALLA_CLIENTE", "ver")
    PANTALLA_CLIENTE_CONTENIDO_VIEW = permission_code("PANTALLA_CLIENTE", "contenido.ver")
    PANTALLA_CLIENTE_CONTENIDO_CREAR = permission_code("PANTALLA_CLIENTE", "contenido.crear")
    PANTALLA_CLIENTE_CONTENIDO_APROBAR = permission_code("PANTALLA_CLIENTE", "contenido.aprobar")
    PANTALLA_CLIENTE_CAMPANA_PROGRAMAR = permission_code("PANTALLA_CLIENTE", "campana.programar")
    PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR = permission_code("PANTALLA_CLIENTE", "publicidad.gestionar")
    PANTALLA_CLIENTE_METRICAS_VIEW = permission_code("PANTALLA_CLIENTE", "metricas.ver")
    INTEGRACIONES_VIEW = permission_code("CONFIGURACION", "integracion.ver")
    INTEGRACIONES_CREAR = permission_code("CONFIGURACION", "integracion.crear")
    INTEGRACIONES_EDITAR = permission_code("CONFIGURACION", "integracion.editar")
    INTEGRACIONES_SECRETOS = permission_code("CONFIGURACION", "integracion.secretos")
    INTEGRACIONES_PROBAR = permission_code("CONFIGURACION", "integracion.probar")
    INTEGRACIONES_ACTIVAR = permission_code("CONFIGURACION", "integracion.activar")
    INTEGRACIONES_DESACTIVAR = permission_code("CONFIGURACION", "integracion.desactivar")
    WEBHOOKS_GESTIONAR = permission_code("CONFIGURACION", "webhook.gestionar")
    FEATURE_FLAGS_VIEW = permission_code("CONFIGURACION", "flag.ver")
    FEATURE_FLAGS_CREAR = permission_code("CONFIGURACION", "flag.crear")
    FEATURE_FLAGS_EDITAR = permission_code("CONFIGURACION", "flag.editar")
    FEATURE_FLAGS_APROBAR = permission_code("CONFIGURACION", "flag.aprobar")
    FEATURE_FLAGS_ACTIVAR = permission_code("CONFIGURACION", "flag.activar")
    APARIENCIA_VIEW = permission_code("CONFIGURACION", "apariencia.ver")
    APARIENCIA_GESTIONAR = permission_code("CONFIGURACION", "apariencia.gestionar")
    TEMA_CREAR = permission_code("CONFIGURACION", "tema.crear")
    TEMA_ACTIVAR = permission_code("CONFIGURACION", "tema.activar")
    NOTIFICACIONES_VIEW = permission_code("CONFIGURACION", "notificacion.ver")
    NOTIFICACIONES_GESTIONAR = permission_code("CONFIGURACION", "notificacion.gestionar")
    OFFLINE_VIEW = permission_code("CONFIGURACION", "offline.ver")
    OFFLINE_GESTIONAR = permission_code("CONFIGURACION", "offline.gestionar")
    USUARIOS_VIEW = permission_code("CONFIGURACION", "usuario.ver")
    USUARIOS_CREAR = permission_code("CONFIGURACION", "usuario.crear")
    USUARIOS_EDITAR = permission_code("CONFIGURACION", "usuario.editar")
    USUARIOS_ACTIVAR = permission_code("CONFIGURACION", "usuario.activar")
    # No USUARIOS_DESBLOQUEAR here — unlock is gated by
    # UserSecurityService.unlock_user()'s own internal permission check
    # against its pre-existing codes (CONFIG_SEGURIDAD.editar /
    # USUARIOS.desbloquear), not a new CONFIGURACION.* code.
    ROLES_VIEW = permission_code("CONFIGURACION", "rol.ver")
    ROLES_CREAR = permission_code("CONFIGURACION", "rol.crear")
    ROLES_EDITAR = permission_code("CONFIGURACION", "rol.editar")
    AUDITORIA_VIEW = permission_code("CONFIGURACION", "auditoria.ver")


ALL_CONFIGURACION_PERMISSIONS = frozenset(
    value for name, value in vars(ConfiguracionPermissions).items() if name.isupper()
)
