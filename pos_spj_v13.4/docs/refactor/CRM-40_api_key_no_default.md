# CRM-40 — Fase 6 (continuación): la API key del gateway REST ya no tiene un valor por defecto adivinable

Fecha: 2026-08-16. A petición del usuario de retomar "FASE 6 —
AUTENTICACIÓN". CRM-28 ya cubrió el núcleo de esta fase (contraseñas:
sin fallback texto plano/SHA-256, fail-fast sin bcrypt). Esta continuación
revisó lo que quedaba: tokens/sesiones y "no confiar en permisos
enviados por el cliente sin verificación".

## Hallazgo

`api/auth.py::_get_configured_key()` — la función que valida el header
`X-API-Key` de TODO el gateway REST (`api/routers/clientes.py`, usado en
producción por WhatsApp per CRM-25/CRM-21) — caía a un valor hardcodeado,
`"dev-only-change-in-production"`, cuando no había ninguna clave real
configurada (ni `ERP_API_KEY` en el entorno, ni
`configuraciones.api_gateway_key` en la BD). El comentario advertía "solo
para desarrollo" pero nada lo impedía en producción — si un despliegue
real olvida configurar la clave, el gateway completo queda abierto con
una contraseña pública y documentada en el propio código fuente. Mismo
patrón exacto que el fallback SHA-256 de contraseñas que CRM-28 ya
eliminó: un valor por defecto "solo para dev" que en la práctica es una
puerta trasera si alguien olvida el paso de configuración.

Confirmado que ningún `.env` real de este repo tiene `ERP_API_KEY`
configurado (`whatsapp_service/.env.example` lo lista vacío) — es decir,
el servidor de este mismo entorno de desarrollo está corriendo hoy con
la clave por defecto pública, sin que nada lo señale.

## Qué se cambió

`_get_configured_key()` retorna `None` cuando no hay clave configurada
(en vez de `_DEFAULT_DEV_KEY`). `verify_api_key()` ahora distingue tres
casos:
- Sin header `X-API-Key` → 401 (sin cambios).
- Servidor sin ninguna clave configurada → **503** (nuevo — rechaza TODAS
  las solicitudes hasta que se configure una clave real, en vez de
  aceptar la conocida).
- Clave incorrecta → 401 (sin cambios, comparación en tiempo constante
  ya existente, `secrets.compare_digest`).

## Verificado, sin cambios necesarios

- **Timeout de sesión**: `SessionTimeoutMonitor` (desktop) confirmado
  realmente instanciado y conectado (`interfaz/main_window.py:918,1050-1061`,
  no solo definido) — cierra sesión por inactividad, emite
  `sesion_expirada` → logout. Ya era real, no un caso de "construido pero
  desconectado".
- **"No confiar en permisos enviados por el cliente sin firma"**: la capa
  REST de Clientes/CRM no acepta ningún claim de permisos del cliente —
  toda autorización se resuelve server-side vía
  `CustomerAuthorizationPolicy`/`CustomerSessionPermissionChecker`
  (verificado en CRM-39), nunca confiando en un campo del payload.

## Explícitamente NO tocado

- **Argon2id**: bcrypt sigue siendo la única ruta activa (aceptable per
  el propio prompt maestro: "bcrypt es aceptable siempre que sea la
  única ruta activa" — ya lo es desde CRM-28). Migrar de bcrypt a
  Argon2id es un cambio de biblioteca mayor, no una corrección de una
  vulnerabilidad activa como esta.
- **Revocación de sesión / invalidación multi-dispositivo**: no existe
  infraestructura para esto (no hay lista de sesiones activas en
  servidor, es una app de escritorio con `SessionContext` en memoria por
  proceso) — no se fabricó un mecanismo decorativo sin nada real a lo
  que conectarlo, mismo criterio que CRM-20/CRM-26 ya aplicaron para
  infraestructura ausente.

## Verificación

```bash
python -m pytest tests/test_crm_40_api_auth_no_default_key.py \
  tests/integration/customers/test_crm_21_read_path_wiring.py -v
```
16 tests pasando (9 nuevos), cero regresiones — el único consumidor de
`verify_api_key` en tests ya lo sobreescribía vía
`app.dependency_overrides`, así que el cambio de comportamiento del
fallback no lo afecta.
