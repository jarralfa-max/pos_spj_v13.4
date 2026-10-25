"""Granular permission catalog for Losses — vocabulario ``MERMA.<accion>``.

Read access never implies mutation or approval.

Auditoría de permisos 968e0bc (PER-04): hasta aquí eran códigos PLANOS
(``LOSSES_APPROVE``) fuera del catálogo, así que NINGÚN permiso de Mermas se
podía conceder desde Configuración: sólo un rol de acceso total podía operar el
módulo. Ahora es el estándar ``MODULO.accion`` (como Compras) bajo la clave
``MERMA`` que ya sembraban los roles; la migración 347 traduce cualquier fila
guardada con el código plano. ``MERMA.ver`` y ``MERMA.exportar`` coinciden a
propósito con las acciones gruesas sembradas: significan lo mismo.
"""


class LossPermissions:
    ACCESS = "MERMA.acceso"
    VIEW = "MERMA.ver"
    VIEW_OWN_BRANCH = "MERMA.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "MERMA.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "MERMA.ver.todas_sucursales"
    VIEW_COST = "MERMA.costo.ver"
    VIEW_AUDIT = "MERMA.auditoria.ver"
    EXPORT = "MERMA.exportar"

    OVERVIEW_VIEW = "MERMA.resumen.ver"
    REGISTRATION_VIEW = "MERMA.registro.ver"
    PENDING_VIEW = "MERMA.pendientes.ver"
    PRODUCTION_VIEW = "MERMA.produccion.ver"
    INVENTORY_VIEW = "MERMA.inventario.ver"
    EXPIRY_DAMAGE_VIEW = "MERMA.caducidad_dano.ver"
    QUALITY_VIEW = "MERMA.calidad.ver"
    YIELD_VIEW = "MERMA.rendimiento.ver"
    RECOVERY_VIEW = "MERMA.recuperacion.ver"
    DISPOSITION_VIEW = "MERMA.disposicion.ver"
    INVESTIGATION_VIEW = "MERMA.investigacion.ver"
    CORRECTIVE_ACTION_VIEW = "MERMA.accion_correctiva.ver"
    ALERT_VIEW = "MERMA.alertas.ver"
    ANALYTICS_VIEW = "MERMA.analisis.ver"
    SETTINGS_VIEW = "MERMA.configuracion.ver"

    REPORT = "MERMA.reportar"
    EDIT_DRAFT = "MERMA.borrador.editar"
    SUBMIT = "MERMA.enviar"
    REVIEW = "MERMA.revisar"
    APPROVE = "MERMA.aprobar"
    REJECT = "MERMA.rechazar"
    POST_INVENTORY = "MERMA.inventario.aplicar"
    REVERSE_INVENTORY = "MERMA.inventario.reversar"
    VALUE_LOSS = "MERMA.valorizar"
    CLOSE = "MERMA.cerrar"
    REOPEN = "MERMA.reabrir"

    APPROVE_OVER_LIMIT = "MERMA.aprobar_sobre_limite"
    PLAN_DISPOSAL = "MERMA.disposicion.planear"
    AUTHORIZE_DISPOSAL = "MERMA.disposicion.autorizar"
    COMPLETE_DISPOSAL = "MERMA.disposicion.completar"
    RECORD_RECOVERY = "MERMA.recuperacion.registrar"
    APPROVE_RECOVERY = "MERMA.recuperacion.aprobar"
    QUALITY_REJECT = "MERMA.calidad.rechazar"
    QUALITY_CONDEMN = "MERMA.calidad.condenar"
    TRANSFER_LINK = "MERMA.transferencia.vincular"
    MANAGE_CLAIMS = "MERMA.reclamaciones.gestionar"

    OPEN_INVESTIGATION = "MERMA.investigacion.abrir"
    INVESTIGATE = "MERMA.investigacion.investigar"
    CONCLUDE_INVESTIGATION = "MERMA.investigacion.concluir"
    MANAGE_ROOT_CAUSE = "MERMA.causa_raiz.gestionar"
    CREATE_CORRECTIVE_ACTION = "MERMA.accion_correctiva.crear"
    VERIFY_CORRECTIVE_ACTION = "MERMA.accion_correctiva.verificar"

    MANAGE_CLASSIFICATIONS = "MERMA.clasificaciones.gestionar"
    MANAGE_REASONS = "MERMA.motivos.gestionar"
    MANAGE_POLICIES = "MERMA.politicas.gestionar"
    MANAGE_NOTIFICATIONS = "MERMA.notificaciones.gestionar"


ALL_LOSS_PERMISSIONS = frozenset(
    value for name, value in vars(LossPermissions).items()
    if not name.startswith("_") and isinstance(value, str)
)
