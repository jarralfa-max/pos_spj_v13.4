
# core/services/auth_service.py
import logging
import hashlib as _hashlib

def _sha256(pwd: str) -> str:
    return _hashlib.sha256(pwd.encode()).hexdigest()

try:
    import bcrypt as _bcrypt
    def _hash_password(pwd: str) -> str:
        return _bcrypt.hashpw(pwd.encode(), _bcrypt.gensalt()).decode()
    def _check_password(pwd: str, hashed: str) -> bool:
        """
        Acepta contraseñas en 3 formatos:
          1. Texto plano (BD legacy que nunca hasheó)
          2. SHA-256 hex (formato usado por el seed inicial de SPJ)
          3. Bcrypt (formato seguro moderno)
        """
        # Texto plano
        if hashed == pwd:
            return True
        # SHA-256 (seed inicial)
        if _sha256(pwd) == hashed:
            return True
        # Bcrypt
        try:
            return _bcrypt.checkpw(pwd.encode(), hashed.encode())
        except Exception:
            return False
except ImportError:
    def _hash_password(pwd: str) -> str:
        return _sha256(pwd)
    def _check_password(pwd: str, hashed: str) -> bool:
        """Acepta texto plano y SHA-256."""
        return hashed == pwd or _sha256(pwd) == hashed

logger = logging.getLogger(__name__)

class AuthService:
    """
    Servicio encargado de la Autenticación, manejo de sesiones y cifrado.
    """
    def __init__(self, auth_repo, security_service, audit_service):
        self.repo = auth_repo
        self.security_service = security_service
        self.audit_service = audit_service

    MAX_INTENTOS = 5
    BLOQUEO_MINUTOS = 15

    def _check_lockout(self, username: str) -> None:
        """Lanza excepción si el usuario está bloqueado por intentos fallidos."""
        try:
            row = self.auth_repo.db.execute(
                """SELECT intentos_fallidos, bloqueado_hasta
                   FROM usuarios WHERE username=?""", (username,)
            ).fetchone()
            if not row:
                return
            if row['bloqueado_hasta']:
                from datetime import datetime
                hasta = datetime.fromisoformat(str(row['bloqueado_hasta']))
                if datetime.now() < hasta:
                    mins = int((hasta - datetime.now()).seconds / 60) + 1
                    raise PermissionError(
                        f"Usuario bloqueado por {mins} min. Demasiados intentos fallidos.")
                else:
                    # Desbloquear si ya pasó el tiempo
                    self.auth_repo.db.execute(
                        "UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE username=?",
                        (username,))
                    try: self.auth_repo.db.commit()
                    except Exception: pass
        except PermissionError:
            raise
        except Exception:
            pass  # Si la columna no existe, ignorar

    def _register_failed_attempt(self, username: str) -> None:
        """Registra intento fallido y bloquea si supera el máximo."""
        try:
            from datetime import datetime, timedelta
            self.auth_repo.db.execute("""
                UPDATE usuarios
                SET intentos_fallidos = COALESCE(intentos_fallidos, 0) + 1,
                    bloqueado_hasta = CASE
                        WHEN COALESCE(intentos_fallidos, 0) + 1 >= ?
                        THEN datetime('now', '+' || ? || ' minutes')
                        ELSE bloqueado_hasta
                    END
                WHERE username=?
            """, (self.MAX_INTENTOS, self.BLOQUEO_MINUTOS, username))
            try: self.auth_repo.db.commit()
            except Exception: pass
        except Exception:
            pass

    def _reset_failed_attempts(self, username: str) -> None:
        """Resetea contador tras login exitoso."""
        try:
            self.auth_repo.db.execute(
                "UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE username=?",
                (username,))
            try: self.auth_repo.db.commit()
            except Exception: pass
        except Exception:
            pass

    def authenticate(self, username: str, plain_password: str) -> dict:
        """
        Valida las credenciales de un usuario.
        Soporta contraseñas hasheadas con bcrypt y texto plano (legacy).
        """
        if not username or not plain_password:
            raise PermissionError("Debe ingresar usuario y contraseña.")

        user_data = self.repo.get_user_by_username(username)
        
        if not user_data:
            self._register_failed_attempt(username)
            self.audit_service.log_change(
                usuario=username, accion="LOGIN_FAILED", modulo="AUTH", entidad="USUARIO",
                entidad_id=username, before_state={}, after_state={}, sucursal_id=0,
                detalles="Intento de acceso con usuario inexistente o inactivo."
            )
            raise PermissionError("Usuario no encontrado o inactivo.")

        db_pass = user_data['password_hash']
        is_valid = False

        # 1. VERIFICACIÓN: Acepta texto plano (legacy) o Bcrypt
        if db_pass == plain_password:
            is_valid = True
            logger.info("Usuario %s autenticado vía texto plano (Legacy). Se recomienda migrar a bcrypt.", username)
            # *Opcional*: Aquí podrías llamar a una función para auto-migrar su contraseña a bcrypt silenciosamente.
        else:
            try:
                # Comparamos el hash con la contraseña en texto plano
                if _check_password(plain_password, db_pass):
                    is_valid = True
            except ValueError:
                pass # Si db_pass no es un hash de bcrypt válido, ignoramos y falla

        if not is_valid:
            self.audit_service.log_change(
                usuario=username, accion="LOGIN_FAILED", modulo="AUTH", entidad="USUARIO",
                entidad_id=str(user_data['id']), before_state={}, after_state={}, sucursal_id=user_data['sucursal_id'],
                detalles="Contraseña incorrecta."
            )
            raise PermissionError("Contraseña incorrecta.")

        # 2. ÉXITO: Cargar permisos RBAC en caché para este usuario/sucursal
        self.security_service.clear_cache()
        try:
            self.security_service.load_permissions(
                usuario_id  = user_data['id'],
                sucursal_id = user_data.get('sucursal_id', 1)
            )
        except Exception as e:
            logger.warning("load_permissions tras login: %s", e)

        # 3. Auditoría de éxito
        self.audit_service.log_change(
            usuario=username, accion="LOGIN_SUCCESS", modulo="AUTH", entidad="USUARIO",
            entidad_id=str(user_data['id']), before_state={}, after_state={}, sucursal_id=user_data['sucursal_id'],
            detalles=f"Inicio de sesión exitoso desde la interfaz. Rol: {user_data['rol']}"
        )

        # Retornamos los datos limpios a la UI para que configure sus botones
        # ⚠️ NUNCA regresamos el password_hash a la UI
        del user_data['password_hash']
        
        logger.info(f"Acceso concedido a {username} ({user_data['rol']}).")
        return user_data

    def login(self, username: str, plain_password: str) -> dict:
        """Alias de authenticate() — compatibilidad con main_window.py."""
        return self.authenticate(username, plain_password)