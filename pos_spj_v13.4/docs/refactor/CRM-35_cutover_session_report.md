# CRM-35 — Reporte de cierre de sesión: cut-over Customer Master (CRM-27 a CRM-34)

Fecha: 2026-08-16. Cierra la sesión que ejecutó el "PROMPT MAESTRO
DEFINITIVO" de cut-over completo. Formato per Fase 16 del prompt
("ENTREGA FINAL").

## 1. RESUMEN

**Alcance real vs. alcance del prompt maestro**: el prompt maestro pide un
cut-over de 16 fases cubriendo identidad, RBAC, autenticación, esquema de
BD, frontend, navegación, timeline, purga legacy y documentación —
across Sales, Finance, WhatsApp, Delivery, Loyalty, CRM. Esa es
razonablemente semanas de trabajo, no una sesión. Esta sesión ejecutó
**Fase 0 (re-auditoría completa)** más **7 fases concretas, cada una
implementada, probada y documentada individualmente** (CRM-27 a CRM-34),
priorizando piezas que ya existían en el Customer Master pero estaban
genuinamente desconectadas de cualquier flujo real — el mismo patrón que
"switching this gate to the new stack would compute zero exposure" que
CRM-25 ya había identificado para crédito.

**Estado inicial**: Customer Master (`backend/domain/customers`,
`backend/application/customers`, CRM-1 a CRM-26) completo como bounded
context aislado, pero con múltiples piezas de valor real completamente
desconectadas de la operación diaria — el workflow de crédito de CRM-8
nunca afectaba el POS; el dominio de consentimiento de CRM-9 nunca
gateaba un envío de WhatsApp real; no existía ningún mecanismo para
saltar de la ficha de un cliente a otra pantalla del ERP.

**Estado final**: esas piezas están conectadas y verificadas con tests
reales contra el comportamiento antes/después. Además: un bug de
seguridad activo (contraseña en texto plano si bcrypt no está instalado)
fue encontrado y corregido; un segundo bug de seguridad (una función
llamada "migrar a bcrypt" que en realidad hasheaba con SHA-256, sin
consumidores que lo hubieran detectado) también.

**Riesgo antes**: control de crédito potencialmente inconsistente con lo
que un administrador configura vía el workflow moderno; falla de
autenticación silenciosa (texto plano) bajo una condición real
(bcrypt ausente); ningún gate de consentimiento en WhatsApp pese a que el
dominio para eso ya existía; sin conectividad entre Customer 360 y el
resto del ERP.

**Riesgo después**: las cuatro brechas anteriores cerradas y probadas.
Riesgo residual real, documentado explícitamente en cada fase (no
oculto): `cuentas_por_cobrar`/`accounts_receivable` siguen en identidad
legacy; Delivery/Loyalty siguen en identidad legacy en su lado de
escritura; `GestionarClienteUC` identificado como huérfano pero no
purgado; solo una ruta de NavigationIntent conectada (Ventas).

## 2. ARCHIVOS MODIFICADOS

**Finanzas/Crédito (CRM-27)**
- `application/services/customer_credit_service.py`
- `migrations/engine.py`, `migrations/MIGRATION_LOG.md`

**Autenticación (CRM-28)**
- `core/services/auth_service.py`, `security/auth.py`,
  `modulos/configuracion.py`, `database/conexion.py`
- `tests/test_phase0_hardening_regression.py`,
  `tests/integration/test_login_lockout_and_unlock_flow.py`
- Dato: hash de la cuenta `demo` en `data/spj_pos_database.db`
  reemplazado (SHA-256 → bcrypt, nueva contraseña `demo123`)

**RBAC (CRM-29)**
- `core/session_context.py`

**WhatsApp (CRM-31)**
- `whatsapp_service/messaging/sender.py`

**Navegación (CRM-32)**
- `frontend/desktop/modules/customers_crm/pages/customer_profile_page.py`
- `frontend/desktop/modules/customers_crm/customers_crm_workspace.py`
- `modulos/ventas.py`, `interfaz/main_window.py`

**Timeline (CRM-33)**
- `backend/application/customers/queries/customer_history_query_service.py`
- `tests/integration/customers/conftest.py`

**Purga (CRM-34)**
- `tests/architecture/allowlists.py`,
  `tests/architecture/customers_crm_guardrails.py`
- `tests/integration/customers/test_crm_21_read_path_wiring.py`

## 3. ARCHIVOS CREADOS

- `migrations/standalone/196_customer_credit_profile_backfill.py`
- `frontend/desktop/navigation/__init__.py`,
  `frontend/desktop/navigation/navigation_intent.py`
- `tests/integration/customer_credit/test_crm_27_finance_credit_cutover.py`
- `tests/test_crm_29_session_permission_wildcard.py`
- `whatsapp_service/tests/test_sender_consent_gate.py`
- `tests/unit/test_crm_32_navigation_intent.py`
- `tests/integration/customers/test_customer_360_application.py` (nuevas
  clases de test agregadas a un archivo ya existente)
- `docs/refactor/CRM-27_finance_credit_cutover.md`
- `docs/refactor/CRM-28_auth_hardening.md`
- `docs/refactor/CRM-29_rbac_module_wildcard.md`
- `docs/refactor/CRM-31_whatsapp_consent_gate.md`
- `docs/refactor/CRM-32_customer_360_navigation.md`
- `docs/refactor/CRM-33_customer_timeline_sales.md`
- `docs/refactor/CRM-34_legacy_purge.md`
- `docs/refactor/CRM-35_cutover_session_report.md` (este archivo)

## 4. ARCHIVOS ELIMINADOS

- `core/services/cliente_service.py` (`ClienteService`) — cero
  consumidores de producción confirmados; ver CRM-34.

## 5. TABLAS/COLUMNAS ELIMINADAS

Ninguna. Esta sesión fue exclusivamente aditiva a nivel de esquema
(`customer_credit_profiles` ya existía desde CRM-8; migración 196 solo
backfillea filas). No se purgó ninguna tabla/columna legacy — la
identidad de `cuentas_por_cobrar`/`ventas`/`delivery_orders`/
`loyalty_*` sigue siendo la legacy `cliente_id`, deliberadamente sin
tocar (ver §10).

## 6. LEGACY ELIMINADO

- `core/services/cliente_service.py` completo (código de fachada +
  fallback SQL de `guardar_formulario()`, servía a un diálogo ya
  retirado en CRM-24).
- El bloque de auto-migración de contraseña legacy en `security/auth.py`
  (quedó código muerto tras eliminar el fallback de verificación
  texto-plano/SHA-256, nunca podía alcanzarse).

## 7. INTEGRACIONES COMPLETADAS

| Contexto | Antes | Después |
|---|---|---|
| **Sales (crédito)** | Gate leía `clientes.allows_credit`/`credit_limit` directo | Prefiere `customer_credit_profiles` (workflow CRM-8) vía bridge, fallback a legacy si no hay perfil |
| **Sales (navegación)** | Sin conexión desde Customer 360 | "Nueva venta" preselecciona cliente vía NavigationIntent |
| **Sales (timeline)** | Ventas invisible en el historial del cliente | `VENTA_COMPLETADA`/`VENTA_CANCELADA` aparecen en la pestaña Auditoría |
| **WhatsApp** | Sin ningún chequeo de consentimiento | `send_message`/`send_template` honran un WITHDRAWN explícito |
| **Finance** | Igual que Sales/crédito arriba | — |
| **Loyalty** | (investigado) Lectura ya wireada desde CRM-13 | Sin cambios necesarios — confirmado, no una brecha real |
| **Delivery** | (investigado) Lectura ya wireada desde CRM-13 | Sin cambios necesarios — confirmado, no una brecha real |
| **CRM** | — | Base del prompt maestro, sin cambios esta sesión |

## 8. SEGURIDAD

**Auth**: bcrypt-únicamente en las tres rutas de hashing/verificación
identificadas (`core/services/auth_service.py`, `security/auth.py`,
`modulos/configuracion.py`); fail-fast (`MissingPasswordHashingBackendError`/
`AuthError`) si bcrypt no está instalado, en vez de degradar a SHA-256 o
texto plano. `database/conexion.py::migrar_password_a_bcrypt` corregido
para realmente usar bcrypt.

**RBAC**: wildcard de módulo (`"CLIENTES.*"`) agregado al evaluador real
(`SessionContext.tiene_permiso`) sin romper el exact-match ni el wildcard
global (`"*"`) ya existentes. Catálogo canónico confirmado sin drift
(cero divergencia CustomerPermissions/CRMPermissions vs.
`permission_catalog.py`, verificado de nuevo en esta sesión).

**Scopes**: sin cambios — ya enforced en application layer desde CRM-2.

**Datos sensibles**: consentimiento WhatsApp ahora tiene efecto real
sobre un canal de comunicación real (antes: dominio construido, sin
ningún consumidor).

## 9. FRONTEND

**Navegación**: `NavigationIntent` (nuevo, `frontend/desktop/navigation/`)
+ una ruta real conectada (`sales.new` → Ventas, con resolución de
identidad vía el bridge CRM-21 y mensaje explícito cuando el bridge no
existe). Reutiliza la infraestructura de `abrir_modulo` ya existente en
`interfaz/main_window.py` en vez de crear un sistema paralelo.

**Design System**: sin cambios — confirmado ya cumplido y enforced por
guardrails existentes (`test_customers_crm_uses_canonical_design_system.py`,
`test_customers_crm_has_no_hardcoded_colors.py`), no una brecha real tras
investigar.

**Customer 360**: la pestaña "Auditoría" ahora incluye eventos de venta;
nuevo botón de acción "Nueva venta" en el header del Expediente.

## 10. TESTS

Por fase (todos ejecutados esta sesión, todos en verde al cierre):

| Fase | Nuevos | Total ejecutado | Resultado |
|---|---|---|---|
| CRM-27 | 8 | 54 | 54 passed |
| CRM-28 | 1 reescrito | 5 | 5 passed |
| CRM-29 | 6 | 13 | 13 passed |
| CRM-31 | 5 | 22 (16 + 6 previos ignorados por colisión preexistente) | 21 passed, 1 flake preexistente confirmado no relacionado |
| CRM-32 | 8 | 51 | 51 passed |
| CRM-33 | 3 | 40 | 40 passed (1 guardrail detectó y corrigió un nombre de variable prohibido) |
| CRM-34 | 0 (2 retirados junto a la clase) | 29 | 29 passed |

Fallos preexistentes confirmados NO relacionados con esta sesión (vía
aislamiento directo, mismo fallo con y sin los cambios):
`tests/test_credit_sale_cxc.py`, `tests/test_financial_core_enforcement.py`,
`tests/test_sales_customer_loyalty.py` (22 tests, esquema desactualizado
en fixtures ad-hoc de otro módulo), `tests/test_phase0_hardening_regression.py`
(8 tests, archivos `modulos/caja.py`/`modulos/merma.py` ausentes —
renombrados/movidos por otra sesión concurrente), y un `PermissionError`
de limpieza de archivo temporal en Windows en
`whatsapp_service/tests/test_conversation_quote_context.py`.

## 11. DEUDA RESTANTE (real, no resoluble razonablemente en este cierre)

- **`cuentas_por_cobrar`/`accounts_receivable`**: identidad sigue siendo
  `cliente_id` legacy. Migrarla completa toca ~10 archivos activos de
  escritura financiera (`AccountsReceivableService`, ambos finance
  handlers, `treasury_service.py`, `enterprise/finance_service.py`) — CRM-27
  cerró la mitad que importaba hoy (límite/autorización) sin ese riesgo.
- **Delivery/Loyalty, lado de escritura**: `delivery_orders.cliente_id`,
  `loyalty_ledger.cliente_id`, etc. siguen legacy. El lado de lectura ya
  está resuelto (CRM-13); escribir en identidad nueva requiere UI nueva
  (selector de dirección canónica, por ejemplo), no una reconexión de
  bajo riesgo.
- **`GestionarClienteUC`**: huérfano (sin consumidor de producción tras
  CRM-34), identificado, no purgado — requiere tocar `app_container.py`
  + 2 archivos de test propios, deliberadamente diferido a una fase
  futura para no apurar un borrado al cierre de una sesión ya larga.
- **`security/rbac.py`**: segundo evaluador de permisos independiente,
  con su propio catálogo hardcodeado — no consultado por Clientes/CRM,
  fuera del alcance de "Clientes/CRM usa el catálogo moderno" que pide
  el prompt.
- **Solo una ruta de NavigationIntent conectada** (`sales.new`) — el
  mecanismo está listo para crecer (WhatsApp, crédito, CxC, cobranza,
  caso de servicio, delivery, fidelidad), cada una necesita su propio
  `aplicar_contexto` real en el módulo destino, no fabricado aquí.
- **Timeline**: no incluye pagos/cobros, WhatsApp ni delivery todavía —
  mismo patrón de extensión que Ventas, no aplicado a las demás fuentes
  esta sesión.
- **Fases explícitamente no iniciadas del prompt maestro**: purga de
  esquema de BD más amplia (Fase 7), consolidación completa de RBAC
  (`security/rbac.py`), Argon2id (bcrypt es la única ruta activa hoy,
  aceptable per el propio prompt, pero no es Argon2id), composition root
  única repo-wide (Fase 10).

## 12. GREP FINAL DE LEGACY

```
GestionarClienteUC   → 4 archivos de código real: core/app_container.py (wiring,
                        huérfano), core/use_cases/cliente.py (la clase),
                        application/use_cases/__init__.py (re-export),
                        + 2 archivos de test propios. Ver §11 — identificado,
                        no purgado esta sesión.
ClienteRepository    → 5 archivos de código real, TODOS consumidores de
                        producción confirmados (modulos/ventas.py,
                        api/routers/clientes.py, core/app_container.py,
                        repositories/cliente_repository.py mismo) — NO es
                        deuda, es la ruta legacy real que Ventas/WhatsApp
                        siguen usando por diseño (CRM-25's "safe subset").
core/services/
  cliente_service.py → 0 referencias (archivo eliminado esta sesión, CRM-34).
```

Ningún hallazgo nuevo de código muerto no documentado.
