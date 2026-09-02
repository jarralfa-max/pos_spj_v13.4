# SHELL-0 — Auditoría de credenciales y seguridad de autenticación

Alcance: los 5 archivos primarios del shell + grep dirigido sobre
`migrations/`, `scripts/`, `security/`, `core/services/`, `services/`,
`integrations/`, `modulos/` (excluyendo `docs/`, `logs/`, `.venv/`, binarios
en `TICKETS/`). Clasificación por hallazgo: **REAL_SECRET** ·
**DEFAULT_CREDENTIAL** · **DEMO_DATA** · **TEST_FIXTURE** · **PLACEHOLDER** ·
**FALSE_POSITIVE**.

## 1. Hallazgo crítico — usuario admin seed con hash SHA-256 sin sal, incompatible con el verificador actual

**Ubicación:** `migrations/m000_base_schema.py`, función `_seed_datos_iniciales`
(o equivalente — bloque "3. Crear Usuario Admin"), líneas 3200-3207:

```python
existe_admin = conn.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone()
if not existe_admin:
    hash_pass = (lambda p: __import__("hashlib").sha256(p.encode()).hexdigest())('admin123')
    conn.execute("""
        INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)
        VALUES (?, 'Administrador Maestro', 'admin', ?, 'admin', ?, 1)
    """, (new_uuid(), hash_pass, INSTALL_BRANCH_UUID))
```

**Clasificación: DEFAULT_CREDENTIAL** (usuario `admin` / contraseña
`admin123`, texto plano en el código fuente de una migración que se ejecuta
en TODO arranque nuevo — ver `application_bootstrap_audit.md` §1, esta
migración corre hasta 2 veces por arranque vía las rutas duplicadas).

**Por qué es doblemente problemático (no solo "hay una contraseña por
defecto"):**

1. **El hash es SHA-256 sin sal**, no bcrypt. `security/auth.py::hash_password()`
   documenta explícitamente: *"Hashea contraseña con bcrypt ... no existe
   fallback a SHA-256 ni a ningún otro esquema más débil."* Este seed viola
   esa regla directamente, generando el hash a mano con `hashlib.sha256`
   dentro de la migración en lugar de reutilizar `security.auth.hash_password`.
2. **`security/auth.py::verify_password()` RECHAZA explícitamente cualquier
   hash que no tenga forma bcrypt** (`if not stored.startswith(("$2b$",
   "$2a$", "$2y$")): return False`, líneas 102-116). Esto significa que el
   usuario `admin`/`admin123` sembrado por la migración **nunca puede
   autenticarse exitosamente** por la ruta de login real — es un
   `DEFAULT_CREDENTIAL` que además está **roto por diseño** (no es
   explotable como puerta trasera, porque el verificador lo rechaza; pero
   tampoco es utilizable como cuenta de arranque legítima).
3. **Efecto operativo:** en una instalación 100% nueva no hay forma
   documentada de iniciar sesión — el único usuario existente (`admin`) no
   puede pasar `verify_password`, y no se encontró ningún script de
   "primer arranque" / `crear_admin.py` / wizard de setup en `scripts/` que
   repare esto (se buscó explícitamente, sin resultados). Esto es a la vez
   un hallazgo de seguridad (contraseña hardcodeada en el repo) y un defecto
   funcional de bootstrap que bloquea el primer uso del sistema.

**Recomendación:** eliminar el hash SHA-256 hardcodeado; sembrar el usuario
admin sin contraseña utilizable (forzar cambio de contraseña en el primer
login) o generar una contraseña aleatoria de un solo uso que se imprima en
log/consola al momento del bootstrap, usando `security.auth.hash_password()`
para producir un hash bcrypt real.

## 2. Hallazgo relacionado — usuario demo con el mismo patrón

**Ubicación:** `migrations/standalone/047_v13_schema.py`, líneas 274-285:

```python
demo_hash = hashlib.sha256("demo".encode()).hexdigest()
conn.execute(
    "INSERT OR IGNORE INTO usuarios "
    "(id,nombre,usuario,password_hash,rol,sucursal_id,activo) "
    "VALUES(?,'Usuario Demo','demo',?,?,?,1)",
    (new_uuid(), demo_hash, 'cajero', INSTALL_BRANCH_UUID))
```

**Clasificación: DEMO_DATA** (usuario `demo`/`demo`, rol `cajero`). Mismo
defecto que el hallazgo #1: hash SHA-256 sin sal, generado igual a mano en
vez de vía `hash_password()`, y por lo tanto también **rechazado** por
`verify_password()` — no es explotable, pero es una cuenta demo inservible
que además dispersa el mismo antipatrón de hashing en un segundo lugar del
código. Confirma que el problema no es un descuido aislado sino un patrón
repetido de "generar `password_hash` a mano con `hashlib.sha256`" en el
código de migraciones, separado del único punto correcto
(`security.auth.hash_password`).

## 3. Mecanismo de hashing de contraseñas — evaluación

**Ubicación:** `security/auth.py`.

- Algoritmo: **bcrypt**, `BCRYPT_ROUNDS = 12`, vía la librería `bcrypt` (con
  detección de disponibilidad `HAS_BCRYPT` y fallo explícito —no
  degradado— si no está instalada).
- `hash_password()` valida longitud mínima (`MIN_PASSWORD_LEN = 8`) antes de
  hashear (`PasswordDebilError` si es muy corta).
- `verify_password()` es estricta: solo acepta hashes con prefijo bcrypt
  (`$2b$`, `$2a$`, `$2y$`); cualquier otra cosa se trata como inválido, nunca
  como comparación de texto plano.
- Rate limiting en memoria por usuario (`MAX_ATTEMPTS = 5`,
  `LOCKOUT_SECONDS = 300`) implementado con locks y diccionarios in-process
  (`_attempts`, `_lockouts`) — funcional para una sola instancia de proceso,
  pero **no persiste entre reinicios ni se comparte entre instancias** (no es
  un problema para este POS de escritorio single-process, pero es una
  limitación a documentar si el shell se expone alguna vez vía API/multi-
  proceso en FASE 6).
- El docstring del módulo menciona *"Auto-migración transparente de texto
  plano → bcrypt al primer login exitoso"*, pero `verify_password()` tal
  como está implementado **rechaza cualquier hash no-bcrypt antes de poder
  verificarlo** — es decir, esa auto-migración no puede dispararse para
  contraseñas legacy en texto plano o SHA-256 existentes, porque la
  verificación ya falla antes de llegar a comparar. Esto es consistente
  (más estricto, "fail closed") con la política declarada de "nunca
  comparación directa de texto plano", pero contradice el comentario de
  auto-migración transparente — vale la pena reconciliar el comentario con
  el comportamiento real, o localizar dónde vive esa migración (no se
  encontró en `security/auth.py`; puede vivir en `AuthService`/
  `AuthRepository` y no se auditó en profundidad por estar fuera de los 5
  archivos primarios).

**¿Cumple estándar clase Argon2id?** No — es bcrypt con costo 12, que es un
algoritmo aceptado y ampliamente usado en producción (resistente a GPU en
comparación con SHA-256/MD5 sin sal), pero **no es Argon2id**, que es el
estándar recomendado actual (OWASP 2023+) por su resistencia superior a
ataques con hardware paralelo (ASIC/GPU) mediante costo de memoria
configurable. Bcrypt-12 es una postura razonable y muy superior a lo que
sembraron las migraciones (§1, §2), pero no alcanza el estándar
"Argon2id-class" que pide el checklist del proyecto. Migrar a Argon2id (p.
ej. vía `argon2-cffi`) sería una mejora incremental fuera del alcance de
SHELL-0 (no toca bootstrap/DI/navegación) pero digna de un ticket propio.

## 4. Otros hallazgos de credenciales / configuración sensible

| Hallazgo | Ubicación | Clasificación | Nota |
|---|---|---|---|
| Credenciales de WhatsApp (`account_sid`, `auth_token_tw`, `meta_token`) | `core/services/whatsapp_service.py` | **FALSE_POSITIVE** (no hardcodeado) | Se leen desde configuración persistida en BD (`_g("wa_account_sid")`, etc.), no hay valores embebidos en el código fuente. |
| MercadoPago (`MercadoPagoService`) | `core/app_container.py:137-142`, `services/mercado_pago_service.py` | **FALSE_POSITIVE** | Construido con `conn=self.db`; no se encontraron tokens/API keys embebidos al auditar el wiring del contenedor (no se auditó el archivo de servicio completo — fuera del alcance de los 5 archivos primarios; recomienda revisión dedicada si no se ha hecho ya). |
| `admin123`, `1234`, `password=` en `tests/**` | Toda la suite de tests (decenas de archivos) | **TEST_FIXTURE** | Contraseñas/PINs de prueba usados para levantar usuarios sintéticos en tests unitarios/integración — no representan credenciales reales ni rutas de producción. No requieren acción. |
| Patrones `1234`/`admin`/`password=` en `logs/*.log*` | `logs/spj_pos.log.*`, `logs/errores.log*` | **FALSE_POSITIVE** | Coincidencias en texto de log (IDs numéricos, mensajes de error), no credenciales — confirmado por muestreo, no son literales de contraseña. |
| Coincidencias binarias de "token"/"secret" en PDFs | `TICKETS/ticket_venta_*.pdf` | **FALSE_POSITIVE** | Ruido de codificación binaria interna del PDF (metadata/streams comprimidos), no texto de credenciales. |
| Passwords/API keys hardcodeadas en `services/`, `integrations/`, `core/services/` (Twilio SID, MercadoPago access token, claves de mapas) | — | **No encontrado** | Grep dirigido (`TWILIO_`, `MERCADOPAGO`, `MP_ACCESS_TOKEN`, `account_sid`, `auth_token=`, `api_key=`) sobre `services/**`, `integrations/**`, `core/services/**` no arrojó valores literales — todo se lee desde configuración/BD. Coincide con el hallazgo previo en memoria del proyecto (`CRM-40_api_key_no_default.md`) de que ya hubo una limpieza de API keys por defecto. |

## 5. `AUTOINCREMENT` / `lastrowid` — verificación REGLA CERO en los 5 archivos primarios

Grep dirigido de `AUTOINCREMENT|lastrowid|int\((product_id|sale_id|branch_id
|customer_id|user_id)\)` sobre `main.py`, `core/app_container.py`,
`core/session_context.py`, `interfaz/main_window.py`,
`interfaz/menu_lateral.py`: **cero coincidencias**. Los 5 archivos que
gobiernan bootstrap/DI/auth/navegación ya son consistentes con REGLA CERO —
no hay identidad entera, ni `lastrowid`, ni casts `int(...)` sobre IDs de
dominio en esta capa. `core/session_context.py` en particular documenta la
regla explícitamente en sus propios comentarios (ver
`application_shell_legacy_inventory.md` §5).

La única fuente de identidad entera relacionada con el hallazgo #1/#2 es el
propio seed de `usuarios`, que **ya usa `new_uuid()`** para el `id` — el
problema ahí no es de identidad (correcto, UUIDv7), es exclusivamente de
hashing de contraseña.

## 6. Resumen de severidad

| # | Hallazgo | Severidad | Explotable hoy | Acción recomendada |
|---|---|---|---|---|
| 1 | Seed `admin`/`admin123` con SHA-256 sin sal | **Alta** (higiene de secretos + bug funcional) | No (rechazado por `verify_password`) | Eliminar hash hardcodeado; forzar cambio de contraseña en primer login o generar password aleatoria de un solo uso vía `hash_password()` |
| 2 | Seed `demo`/`demo` con SHA-256 sin sal | Media (mismo patrón, cuenta demo) | No (rechazado por `verify_password`) | Igual que #1, o eliminar el seed si no se usa en ningún flujo de demo activo |
| 3 | bcrypt-12 en vez de Argon2id | Baja/informativa | N/A | Ticket separado, fuera de alcance de SHELL-0 |
| 4 | Comentario de "auto-migración texto plano → bcrypt" no verificado en `security/auth.py` | Baja (documentación posiblemente desactualizada) | N/A | Confirmar dónde vive esa lógica (si existe) fuera de los 5 archivos primarios |

---

*Generado en FASE SHELL-0 (auditoría). No se modificó ningún archivo de aplicación, incluidas las migraciones referenciadas arriba — el hallazgo se documenta, no se corrige, por estar fuera del alcance de esta fase.*
