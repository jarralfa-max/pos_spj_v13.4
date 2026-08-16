# CRM-27 — Finance/Crédito: el gate real de checkout empieza a usar Customer Master (parte 1 de N)

Fecha: 2026-08-16. Primera fase implementada del cut-over completo pedido
por el usuario (mapa Fase 0 completo: Finance/CxC, Auth/RBAC,
Delivery/Loyalty/WhatsApp, DB schema + frontend — 4 auditorías en paralelo).
Documentado aquí solo lo que esta fase entrega; el resto del mapa queda en
`docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md` §15 y las fases
siguientes (CRM-28 en adelante).

## Qué bloqueaba esto (CRM-25's gap explícito)

CRM-25 dejó documentado, explícitamente fuera de alcance: cambiar
`container.customer_credit_service.validate_credit` (el único enforcement
real del límite de crédito en checkout) al Customer Master nuevo, porque
`cuentas_por_cobrar.cliente_id` nunca se migró y hacerlo hoy habría
computado exposición cero para clientes que solo existen en el modelo
nuevo — una regresión de control financiero real.

Investigación de esta fase (agente de auditoría dedicado) encontró algo
más específico y ya resuelto en la arquitectura: el bounded context
`customer_credit` (CRM-8, migración 188) ya tiene un workflow completo
—request/review/approve/suspend/block/reopen/close, permission-gated, con
segregación de funciones real— sobre `customer_credit_profiles`
(`customer_id`-keyed). Pero **nadie lo consumía**: el gate de checkout
seguía leyendo `clientes.allows_credit`/`clientes.credit_limit`
directamente. Aprobar crédito por el workflow moderno no tenía ningún
efecto en POS — trabajo muerto desde CRM-8.

## Qué se construyó

- **Migración 196** (`migrations/standalone/196_customer_credit_profile_backfill.py`):
  para todo `clientes` legacy con `allows_credit=1 AND credit_limit>0`,
  bridgea (CRM-21, `ResolveLegacyCustomerUseCase`/`BackfillLegacyCustomersUseCase`)
  y crea un `customer_credit_profiles` AUTHORIZED espejo del estado legacy
  actual. Bypassa el workflow de permisos/SoD (mismo criterio que
  `ResolveLegacyCustomerUseCase` ya usa para el bridge) porque no es una
  decisión de negocio nueva, es un espejo 1:1. **Nunca pisa un perfil ya
  existente**, sin importar su estado — si alguien ya usó el workflow
  moderno (p.ej. SUSPENDED), la migración lo respeta.
- **`CustomerCreditService.get_customer()`** (`application/services/customer_credit_service.py`):
  ahora resuelve el `customer_id` bridgeado y, si existe un
  `customer_credit_profiles`, lo usa como fuente de verdad para
  `allows_credit`/`credit_limit` (`profile.is_usable_for_credit_sale()`,
  `profile.credit_limit`) — el workflow moderno ahora tiene efecto real.
  Si no hay perfil bridgeado (cliente nuevo, o un esquema de test aislado
  sin las tablas de Customer Master) cae de vuelta a las columnas legacy
  de `clientes`, exactamente el comportamiento de antes — nunca una
  dependencia dura, mismo criterio defensivo que CRM-25 ya estableció para
  el eligibility check ("try new stack, fallback to legacy, never let a
  new-stack failure block checkout").

## Explícitamente NO tocado en esta fase (documentado, no un olvido)

- **`cuentas_por_cobrar`/`accounts_receivable`**: siguen keyed por el
  `cliente_id` legacy, sin cambios. La exposición/saldo (§40: "Finanzas es
  dueño de documentos/vencimientos/pagos/saldo") sigue viniendo de ahí sin
  tocar — ya existe `CustomerAccountsReceivableSummaryQuery`
  (`backend/application/customer_credit/queries/`), que documenta
  explícitamente por qué se llama con el id legacy hoy. Migrar el propio
  esquema de `cuentas_por_cobrar` a `customer_id` es un cambio de mayor
  alcance (toca `AccountsReceivableService`/Tesorería, un sistema paralelo
  con sus propios consumidores) — deuda documentada para una fase
  siguiente, no bloqueante para lo que esta fase entrega.
- **`clientes.credit_balance`/`saldo`**: la caché legacy sigue
  escribiéndose exactamente igual (`register_credit_sale`,
  `CreditSaleFinanceHandler`, `SaleCancelledFinanceHandler` — cero
  cambios). Eliminarla habría roto ~15 tests de regresión existentes que
  verifican ese comportamiento byte a byte (incluida una prueba que
  introspecciona el código fuente de `validate_credit` buscando el string
  literal `"credit_balance"`) sin aportar nada al objetivo real de esta
  fase (que el LÍMITE/AUTORIZACIÓN sea del Customer Master, no cómo se
  cachea la exposición).
- `modulos/ventas.py`: **cero cambios**. Sigue llamando
  `_ccs.validate_credit(self.cliente_actual['id'], _financed)` con el id
  legacy tal cual — la resolución a `customer_id` ahora ocurre
  transparentemente dentro de `CustomerCreditService`. Migrar la propia
  selección de cliente en Ventas a identidad Customer Master es un cambio
  de mayor alcance, no necesario para que este gate funcione.

## Verificación

```bash
python -m pytest tests/integration/customer_credit/ \
  tests/integration/test_credit_sale_requires_valid_customer.py \
  tests/integration/test_credit_sale_creates_cxc_and_updates_balance.py \
  tests/architecture/test_customers_crm_does_not_duplicate_cxc.py -v
```
54 tests pasando (8 nuevos de esta fase + 46 preexistentes, cero
regresiones) + el guardrail de no-duplicar-CxC sigue verde.

Nota: `tests/test_credit_sale_cxc.py`, `tests/test_financial_core_enforcement.py`
y `tests/test_sales_customer_loyalty.py` tienen fallos preexistentes
(confirmados idénticos con y sin los cambios de esta fase, vía
`git stash`/comparación directa) — no relacionados con CRM-27, no
tocados por esta fase.

## Pendiente (siguientes fases del cut-over)

- Migrar `cuentas_por_cobrar`/`accounts_receivable` a `customer_id` nativo
  (identidad, no solo lectura preferente).
- Extender el mismo patrón bridge+preferencia a Delivery y Loyalty
  (mismo hallazgo de la auditoría: ambos siguen 100% legacy, sin bridge
  usado en la práctica).
- Consolidar `clientes.credit_balance` hacia el nuevo stack cuando ya no
  tenga consumidores legacy (purge, fase posterior).
