class LogisticsPermissionDeniedError(PermissionError):
    pass


class LogisticsAuthorizationPolicy:
    def __init__(self, checker=None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission: str) -> None:
        if self._checker is None or not user_id or not self._checker.has_permission(user_id, permission):
            raise LogisticsPermissionDeniedError(f"Permiso requerido: {permission}")


class LogisticsPermissions:
    """Canonical `MODULO.accion` codes (see core/security/permission_catalog.py)."""

    SHIPMENT_VIEW = "LOGISTICA.embarque.ver"
    SHIPMENT_CREATE = "LOGISTICA.embarque.crear"
    CONTAINER_MANAGE = "LOGISTICA.contenedor.gestionar"
    CONTAINER_ATTACH = "LOGISTICA.contenedor.adjuntar"
    CONTAINER_MOVE = "LOGISTICA.contenedor.mover"
    CONTAINER_SEAL = "LOGISTICA.contenedor.sellar"
    SHIPMENT_DISPATCH = "LOGISTICA.embarque.despachar"
    SHIPMENT_OVERRIDE = "LOGISTICA.embarque.forzar"
    CONTAINER_RELEASE = "LOGISTICA.contenedor.liberar"
    LABEL_PRINT = "LOGISTICA.etiqueta.imprimir"
    CONTAINER_SCAN = "LOGISTICA.contenedor.escanear"
