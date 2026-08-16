# CRM-28 — Autenticación: eliminar fallback débil (fail-fast, sin plaintext/SHA-256)

Fecha: 2026-08-16. Segunda fase del cut-over completo (mapa Fase 0 §Auth/RBAC).

## Hallazgo (auditoría dedicada)

Tres rutas de hashing/verificación de contraseñas coexistían, las tres con
degradación silenciosa cuando `bcrypt` no está instalado:

1. `core/services/auth_service.py` (la ÚNICA realmente wireada al login —
   `interfaz/main_window.py` llama `self.auth_service.authenticate()`):
   `_check_password` aceptaba texto plano, SHA-256 ("formato usado por el
   seed inicial de SPJ") o bcrypt, en ese orden. Sin bcrypt instalado,
   `_hash_password` generaba SHA-256 para contraseñas nuevas.
2. `security/auth.py` (módulo "enterprise" paralelo, no wireado al login
   real pero código vivo, importado por `database/conexion.py`):
   `hash_password` caía a SHA-256 sin bcrypt; `verify_password` aceptaba
   comparación de texto plano directa para cualquier hash sin prefijo
   bcrypt.
3. `modulos/configuracion.py` (crear/editar usuario, UI): si `bcrypt` no
   importaba, escribía la contraseña **en texto plano** directo a
   `password_hash` — el peor de los tres, sin siquiera un hash débil.

Además: `database/conexion.py::migrar_password_a_bcrypt` — pese al nombre,
hasheaba con SHA-256 (`bcrypt` importado pero nunca usado), un bug de
seguridad silencioso sin consumidores que lo hubiera detectado.

Dato real de la base de dev (`data/spj_pos_database.db`): `admin` ya
bcrypt; `demo` tenía un hash SHA-256 (64 hex, formato del seed inicial).

## Qué se cambió

- `core/services/auth_service.py`: `_hash_password`/`_check_password`
  ahora son bcrypt-únicamente. Sin bcrypt instalado, lanzan
  `MissingPasswordHashingBackendError` (fail-fast) — no hay fallback más
  débil. `authenticate()`: eliminadas las ramas `is_plain_legacy`/
  `is_sha_legacy` y el bloque de auto-migración transparente asociado —
  un hash que no es bcrypt válido se trata como contraseña incorrecta.
- `security/auth.py`: mismo criterio — `hash_password` lanza `AuthError`
  sin bcrypt; `verify_password` rechaza cualquier hash sin prefijo
  bcrypt (ya no cae a comparación de texto plano). El bloque de
  auto-migración en `autenticar()` quedó código muerto tras el cambio
  (nunca se alcanzaba: `verify_password` ya rechazaba antes de llegar
  ahí) — eliminado.
- `modulos/configuracion.py`: crear/editar usuario ahora falla con un
  error claro si `bcrypt` no está disponible, en vez de guardar la
  contraseña en texto plano.
- `database/conexion.py::migrar_password_a_bcrypt`: corregido para
  realmente usar bcrypt (coincide con lo que su nombre siempre prometió);
  quitado el `except Exception: pass` que ocultaba el bug.
- **Dato**: el hash SHA-256 de `demo` en `data/spj_pos_database.db` fue
  reemplazado por un hash bcrypt de la contraseña `demo123` — ese hash ya
  no podía verificarse tras el cambio (SHA-256 no es reversible; no hay
  forma de "migrarlo" sin conocer la contraseña en texto plano). `admin`
  no se tocó (ya era bcrypt). **Nueva contraseña de la cuenta `demo`:
  `demo123`.**

## Explícitamente NO tocado en esta fase

- Argon2id (el master prompt lo prefiere pero acepta bcrypt "siempre que
  sea la única ruta activa" — ya lo es, tras este cambio, en los tres
  módulos). Migrar de bcrypt a Argon2id es un cambio de biblioteca mayor,
  no requerido para cerrar el hueco de seguridad real (el fallback
  débil), fuera de alcance aquí.
- Sesiones/tokens (`core/session_context.py`, `core/auth/session_timeout.py`)
  — ya tienen expiración por inactividad; no se encontró vulnerabilidad
  específica que arreglar en esta fase.
- `security/rbac.py` y su catálogo de permisos hardcodeado independiente
  — es un problema de RBAC, no de autenticación; se trata en CRM-29.

## Verificación

```bash
python -m pytest tests/test_phase0_hardening_regression.py::test_auth_service_rejects_plaintext_stored_password \
  tests/test_phase0_hardening_regression.py::test_auth_repository_detects_password_column_and_migrates \
  tests/test_phase0_hardening_regression.py::test_auth_service_failed_attempt_uses_usuario_column \
  tests/test_phase0_hardening_regression.py::test_auth_service_registers_failed_attempt_on_wrong_password \
  tests/integration/test_login_lockout_and_unlock_flow.py -v
```
5 tests pasando (1 reescrito para verificar el nuevo comportamiento
fail-closed — antes verificaba la auto-migración de texto plano, ahora
verifica que se rechaza; 1 fixture actualizado de SHA-256 a bcrypt real,
mismo comportamiento de lockout/desbloqueo bajo prueba, sin pérdida de
cobertura).

Otros 8 fallos en `tests/test_phase0_hardening_regression.py` (archivos
`modulos/caja.py`/`modulos/merma.py` ausentes, tablas `event_outbox`
faltantes, etc.) son preexistentes y no relacionados con autenticación —
no tocados por esta fase.
