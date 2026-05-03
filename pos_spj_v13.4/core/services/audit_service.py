
# core/services/audit_service.py
import json
import logging

logger = logging.getLogger(__name__)

class AuditService:
    """
    Orquestador de Auditoría. 
    Transforma los estados 'Antes' y 'Después' en JSON para trazabilidad.
    """
    def __init__(self, audit_repo):
        self.repo = audit_repo

    def log_change(self, usuario: str, accion: str, modulo: str, entidad: str,
                   entidad_id: str = "",
                   before_state: dict = None,
                   after_state: dict = None,
                   sucursal_id: int = 1,
                   detalles: str = ""):
        """
        Registra un cambio de estado en la base de datos.
        
        :param accion: Ej. 'UPDATE', 'DELETE', 'CANCEL', 'ADJUST'
        :param modulo: Ej. 'INVENTARIO', 'VENTAS', 'CLIENTES'
        """
        # Convertimos los diccionarios a strings JSON para guardarlos de forma estructurada
        before_json = json.dumps(before_state, ensure_ascii=False) if before_state else "{}"
        after_json = json.dumps(after_state, ensure_ascii=False) if after_state else "{}"

        self.repo.insert_audit_log(
            usuario=usuario,
            accion=accion,
            modulo=modulo,
            entidad=entidad,
            entidad_id=str(entidad_id),
            valor_antes=before_json,
            valor_despues=after_json,
            sucursal_id=sucursal_id,
            detalles=detalles
        )
        logger.debug(f"Auditoría: {accion} en {entidad} ID {entidad_id} por {usuario}.")

    def registrar(self, accion: str, entidad: str, entidad_id: int,
                  usuario_id: int, datos_antes: dict = None,
                  datos_despues: dict = None, ip: str = None) -> None:
        """
        Alias de log_change() para compatibilidad con spec v13.4.
        Firma normalizada usada por decoradores y handlers del EventBus.
        """
        self.log_change(
            usuario=str(usuario_id),
            accion=accion,
            modulo=entidad,
            entidad=entidad,
            entidad_id=str(entidad_id),
            before_state=datos_antes,
            after_state=datos_despues,
        )