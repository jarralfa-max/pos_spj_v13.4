
# core/security/decorators.py
from functools import wraps
from core.services.security_service import PermissionDeniedError

def require_permission(permission_code: str):
    """
    Decorador RBAC para proteger métodos dentro de los Servicios.
    Asume que la clase donde se usa tiene 'self.security_service'.
    También asume que el método recibe 'user_id' y 'branch_id' en sus argumentos.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extraemos user_id y branch_id de los argumentos (kwargs o args)
            user_id = kwargs.get('user_id')
            branch_id = kwargs.get('branch_id')
            
            # Validación de seguridad dura
            if not user_id or not branch_id:
                raise PermissionDeniedError("Faltan credenciales de seguridad (user_id/branch_id) para esta operación.")
                
            # Llamamos al SecurityService inyectado en la clase (ej. self.security_service)
            self.security_service.enforce(user_id, branch_id, permission_code)
            
            # Si pasa la validación, ejecutamos la función original
            return func(self, *args, **kwargs)
        return wrapper
    return decorator