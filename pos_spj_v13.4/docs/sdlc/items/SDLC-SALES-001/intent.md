# SDLC-SALES-001 — Falla del motor de precios cobra en silencio el precio de catálogo

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`); confirmado por `inputs/correcciones.md` C-05 (oleada 1)
- **Estado:** borrador
- **Depende de:** SDLC-CORE-012

## Problema
`pricing_resolution.py` atrapa cualquier excepción del motor y devuelve `None`; Ventas entonces usa el precio del catálogo. La bandera `below_minimum` del resolvedor tampoco llega a Ventas (la fachada sólo entrega el número). Un cliente con precio pactado puede ser cobrado a otro importe sin aviso, y un precio bajo el mínimo no exige autorización.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/pricing_resolution.py:25-28` — `except Exception` → `return None` ("se cobra el precio del catálogo") *(verificado directamente en el triage)*
- `PricingReadFacade.sale_price_amount` y `backend/infrastructure/integrations/sales_pricing_client.py` (`effective_price`) devuelven sólo el monto
- Auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 (P0 precio resuelto); los archivos no cambiaron desde entonces (`git diff 9f7d9f61 HEAD`) *(verificado directamente en el triage)*

**Re-verificado el 2026-10-31 sobre `4639fed2` (correcciones C-05):**
- `backend/application/sales/pricing_resolution.py:1-7` — el docstring lo declara como regla: «si no responde o el producto no tiene precio, devuelve None y manda el del catálogo. Nunca bloquea la venta»; `:25-28` sin cambios.
- `backend/application/pricing/queries/pricing_read_facade.py:57-59` — `sale_price_amount` devuelve `self.sale_price(...).price` y descarta el resto del resultado (origen, mínimo, `below_minimum`).
- `backend/infrastructure/integrations/sales_pricing_client.py:47-54` — `effective_price` delega en `sale_price_amount`.
- Ninguna prueba fija hoy este comportamiento: `grep resolve_sale_price tests` = 0 resultados (la red de protección la agrega SDLC-CORE-012).

## Impacto
Cajero/cliente: importe incorrecto cobrado sin rastro; finanzas: margen y acuerdos comerciales no respetados.

## Objetivo
- Ventas distingue 'sin precio configurado' de 'falló el motor'.
- Ante falla del motor la línea no se agrega (o se agrega sólo con autorización trazada), nunca con catálogo en silencio.
- El resultado de precio transporta origen, versión, mínimo y estado; bajo mínimo exige autorización registrada.

## Alcance
- **Incluye:** Contrato de resultado de precio entre Pricing y Sales, manejo de error en POS, pruebas.
- **No incluye:** Revisión puntual de precios en listas aprobadas (SDLC-PRICE-001) y asignación de listas por cliente (SDLC-PRICE-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría integral 2026-10-26; memoria Fase 5 (mínimo con autorización, `AuthorizerPermissionChecker`); `inputs/correcciones.md` C-05.

## Preguntas abiertas
- Ante falla del motor: ¿bloquear la línea o permitir catálogo con autorización de gerente? (misma pregunta que `inputs/correcciones.md` C-05)
