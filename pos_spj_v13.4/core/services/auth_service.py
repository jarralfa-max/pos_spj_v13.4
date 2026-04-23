
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

    def _user_column(self) -> str:
        """Detecta columna de usuario para compatibilidad (usuario/username)."""
        try:
            cols = self.repo.db.execute("PRAGMA table_info(usuarios)").fetchall()
            names = {c[1] for c in cols}
            if "usuario" in names:
                return "usuario"
            if "username" in names:
                return "username"
        except Exception:
            pass
        return "usuario"

    def _check_lockout(self, username: str) -> None:
        """Lanza excepción si el usuario está bloqueado por intentos fallidos."""
        try:
            user_col = self._user_column()
            row = self.repo.db.execute(
                f"""SELECT intentos_fallidos, bloqueado_hasta
                   FROM usuarios WHERE {user_col}=?""", (username,)
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
                    self.repo.db.execute(
                        f"UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE {user_col}=?",
                        (username,))
                    try: self.repo.db.commit()
                    except Exception: pass
        except PermissionError:
            raise
        except Exception:
            pass  # Si la columna no existe, ignorar

    def _register_failed_attempt(self, username: str) -> None:
        """Registra intento fallido y bloquea si supera el máximo."""
        try:
            user_col = self._user_column()
            from datetime import datetime, timedelta
            self.repo.db.execute(f"""
                UPDATE usuarios
                SET intentos_fallidos = COALESCE(intentos_fallidos, 0) + 1,
                    bloqueado_hasta = CASE
                        WHEN COALESCE(intentos_fallidos, 0) + 1 >= ?
                        THEN datetime('now', '+' || ? || ' minutes')
                        ELSE bloqueado_hasta
                    END
                WHERE {user_col}=?
            """, (self.MAX_INTENTOS, self.BLOQUEO_MINUTOS, username))
            try: self.repo.db.commit()
            except Exception: pass
        except Exception:
            pass

    def _reset_failed_attempts(self, username: str) -> None:
        """Resetea contador tras login exitoso."""
        try:
            user_col = self._user_column()
            self.repo.db.execute(
                f"UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE {user_col}=?",
                (username,))
            try: self.repo.db.commit()
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

        # Bloqueo preventivo por intentos fallidos
        self._check_lockout(username)

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

        # 1. VERIFICACIÓN: soporta formatos legacy y modernos.
        is_plain_legacy = (db_pass == plain_password)
        is_sha_legacy = (_sha256(plain_password) == db_pass)
        if is_plain_legacy:
            is_valid = True
            logger.warning("Usuario %s autenticado vía texto plano (legacy).", username)
        else:
            try:
                if _check_password(plain_password, db_pass):
                    is_valid = True
            except ValueError:
                pass

        if not is_valid:
            self._register_failed_attempt(username)
            self.audit_service.log_change(
                usuario=username, accion="LOGIN_FAILED", modulo="AUTH", entidad="USUARIO",
                entidad_id=str(user_data['id']), before_state={}, after_state={}, sucursal_id=user_data['sucursal_id'],
                detalles="Contraseña incorrecta."
            )
            raise PermissionError("Contraseña incorrecta.")

        # 1.1 Auto-migración transparente a hash fuerte si venía en formato legacy
        if is_plain_legacy or is_sha_legacy:
            try:
                new_hash = _hash_password(plain_password)
                if self.repo.migrate_password_hash(user_data['id'], new_hash):
                    self.audit_service.log_change(
                        usuario=username, accion="PASSWORD_REHASHED", modulo="AUTH", entidad="USUARIO",
                        entidad_id=str(user_data['id']), before_state={}, after_state={}, sucursal_id=user_data['sucursal_id'],
                        detalles="Hash de contraseña migrado automáticamente a formato fuerte."
                    )
            except Exception as e:
                logger.warning("No se pudo migrar hash de %s: %s", username, e)

        # 2. ÉXITO: Cargar permisos RBAC en caché para este usuario/sucursal
        self._reset_failed_attempts(username)
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
