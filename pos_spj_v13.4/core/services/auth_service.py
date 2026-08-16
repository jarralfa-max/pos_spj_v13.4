
# core/services/auth_service.py
import logging

try:
    import bcrypt as _bcrypt
except ImportError:
    _bcrypt = None

logger = logging.getLogger(__name__)


class MissingPasswordHashingBackendError(RuntimeError):
    """bcrypt no está instalado. No hay fallback: hashear o verificar una
    contraseña sin un backend criptográfico real (SHA-256 sin sal, o texto
    plano) es una vulnerabilidad, no una degradación aceptable — fail fast
    en vez de silenciosamente debilitar la seguridad de todas las cuentas."""


def _hash_password(pwd: str) -> str:
    if _bcrypt is None:
        raise MissingPasswordHashingBackendError(
            "bcrypt no está instalado. Ejecute 'pip install bcrypt' — no existe "
            "una ruta alterna para hashear contraseñas."
        )
    return _bcrypt.hashpw(pwd.encode(), _bcrypt.gensalt()).decode()


def _check_password(pwd: str, hashed: str) -> bool:
    """Verifica contra bcrypt únicamente. Ningún otro formato (texto plano,
    SHA-256) es aceptado como válido — ver `MissingPasswordHashingBackendError`."""
    if _bcrypt is None:
        raise MissingPasswordHashingBackendError(
            "bcrypt no está instalado. Ejecute 'pip install bcrypt' — no existe "
            "una ruta alterna para verificar contraseñas."
        )
    try:
        return _bcrypt.checkpw(pwd.encode(), hashed.encode())
    except (ValueError, TypeError):
        # hashed no tiene forma de hash bcrypt válido (p.ej. un hash legacy
        # SHA-256/texto plano que no fue migrado) — inválido, no una excepción.
        return False

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

    def _audit_safe(self, **kwargs) -> None:
        """Escribe en el audit trail sin dejar que un fallo del sink enmascare
        el resultado de la autenticación. Un error del audit NUNCA debe
        convertir un rechazo de credenciales en una excepción no controlada
        (que en PyQt aborta la app sin mostrar el mensaje de error)."""
        try:
            self.audit_service.log_change(**kwargs)
        except Exception as e:
            logger.warning("audit log_change falló (no bloquea el login): %s", e)

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
            self._audit_safe(
                usuario=username, accion="LOGIN_FAILED", modulo="AUTH", entidad="USUARIO",
                entidad_id=username, before_state={}, after_state={}, sucursal_id="",
                detalles="Intento de acceso con usuario inexistente o inactivo."
            )
            # Mensaje genérico (no revela si falló el usuario o la contraseña).
            raise PermissionError("Usuario o contraseña incorrectos.")

        db_pass = user_data['password_hash']

        # VERIFICACIÓN: bcrypt únicamente. Sin fallback a texto plano ni
        # SHA-256 — una cuenta con un hash legacy no migrado simplemente no
        # puede autenticarse hasta que un administrador le asigne una
        # contraseña nueva (ver `MissingPasswordHashingBackendError` y
        # CRM-28 en migrations/MIGRATION_LOG.md para el reset ya aplicado
        # a las cuentas que tenían hashes legacy al momento del cutover).
        is_valid = _check_password(plain_password, db_pass or "")

        if not is_valid:
            self._register_failed_attempt(username)
            self._audit_safe(
                usuario=username, accion="LOGIN_FAILED", modulo="AUTH", entidad="USUARIO",
                entidad_id=str(user_data['id']), before_state={}, after_state={}, sucursal_id=user_data['sucursal_id'],
                detalles="Contraseña incorrecta."
            )
            # Mensaje genérico (no revela si falló el usuario o la contraseña).
            raise PermissionError("Usuario o contraseña incorrectos.")

        # 2. ÉXITO: Cargar permisos RBAC en caché para este usuario/sucursal
        self._reset_failed_attempts(username)
        self.security_service.clear_cache()
        try:
            self.security_service.load_permissions(
                usuario_id  = user_data['id'],
                sucursal_id = user_data.get('sucursal_id') or ""
            )
        except Exception as e:
            logger.warning("load_permissions tras login: %s", e)

        # 3. Auditoría de éxito
        self._audit_safe(
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
