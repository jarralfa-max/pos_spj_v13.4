"""Granular permission catalog — ``TRANSFERENCIAS.<accion>``. Use cases must
validate these server-side.

Auditoría de permisos 968e0bc (PER-04): eran códigos planos (``TRANSFERS_*``)
fuera del catálogo y el verificador de sesión sólo traducía tres; aprobar,
surtir, despachar y recibir se denegaban a TODOS, administrador incluido.
``recibir`` coincide con la acción gruesa ya declarada en el catálogo."""
class TransferPermissions:
    ACCESS = "TRANSFERENCIAS.acceso"; DASHBOARD_VIEW = "TRANSFERENCIAS.tablero.ver"
    VIEW_OWN_BRANCH = "TRANSFERENCIAS.ver.sucursal_propia"; VIEW_ASSIGNED_BRANCHES = "TRANSFERENCIAS.ver.sucursales_asignadas"; VIEW_ALL_BRANCHES = "TRANSFERENCIAS.ver.todas_sucursales"; EXPORT = "TRANSFERENCIAS.exportar"; AUDIT_VIEW = "TRANSFERENCIAS.auditoria.ver"
    REQUEST_VIEW = "TRANSFERENCIAS.solicitud.ver"; REQUEST_CREATE = "TRANSFERENCIAS.solicitud.crear"; REQUEST_EDIT = "TRANSFERENCIAS.solicitud.editar"; REQUEST_SUBMIT = "TRANSFERENCIAS.solicitud.enviar"; REQUEST_CANCEL = "TRANSFERENCIAS.solicitud.cancelar"
    APPROVE = "TRANSFERENCIAS.aprobar"; REJECT = "TRANSFERENCIAS.rechazar"; PARTIAL_APPROVE = "TRANSFERENCIAS.aprobar_parcial"; OVERRIDE_LIMIT = "TRANSFERENCIAS.exceder_limite"
    RESERVE = "TRANSFERENCIAS.reservar"; ALLOCATE = "TRANSFERENCIAS.asignar"; PICK = "TRANSFERENCIAS.surtir"; PICK_OVERRIDE_LOT = "TRANSFERENCIAS.surtir.cambiar_lote"; PICK_CONFIRM = "TRANSFERENCIAS.surtir.confirmar"
    DISPATCH_VIEW = "TRANSFERENCIAS.despacho.ver"; DISPATCH = "TRANSFERENCIAS.despachar"; PARTIAL_DISPATCH = "TRANSFERENCIAS.despachar_parcial"; CANCEL_SHIPMENT = "TRANSFERENCIAS.embarque.cancelar"
    RECEIVE_VIEW = "TRANSFERENCIAS.recepcion.ver"; RECEIVE = "TRANSFERENCIAS.recibir"; PARTIAL_RECEIVE = "TRANSFERENCIAS.recibir_parcial"; BLIND_RECEIVE = "TRANSFERENCIAS.recibir_a_ciegas"; RECEIVE_OVER_TOLERANCE = "TRANSFERENCIAS.recibir_sobre_tolerancia"; MANUAL_WEIGHT_OVERRIDE = "TRANSFERENCIAS.peso.capturar_manual"
    DIFFERENCE_VIEW = "TRANSFERENCIAS.diferencia.ver"; DIFFERENCE_REVIEW = "TRANSFERENCIAS.diferencia.revisar"; DIFFERENCE_RESOLVE = "TRANSFERENCIAS.diferencia.resolver"; DIFFERENCE_ACCEPT = "TRANSFERENCIAS.diferencia.aceptar"; DIFFERENCE_REJECT = "TRANSFERENCIAS.diferencia.rechazar"
    RETURN_CREATE = "TRANSFERENCIAS.devolucion.crear"; RETURN_APPROVE = "TRANSFERENCIAS.devolucion.aprobar"; RETURN_DISPATCH = "TRANSFERENCIAS.devolucion.despachar"; REVERSE = "TRANSFERENCIAS.reversar"
    PRINT = "TRANSFERENCIAS.imprimir"; REPRINT = "TRANSFERENCIAS.reimprimir"
    SETTINGS_VIEW = "TRANSFERENCIAS.configuracion.ver"; SETTINGS_MANAGE = "TRANSFERENCIAS.configuracion.gestionar"; NOTIFICATIONS_MANAGE = "TRANSFERENCIAS.notificaciones.gestionar"; WHATSAPP_ALERTS_MANAGE = "TRANSFERENCIAS.whatsapp.gestionar"


ALL_TRANSFER_PERMISSIONS = frozenset(value for name, value in vars(TransferPermissions).items() if name.isupper())
