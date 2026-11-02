# SDLC-FIN-002 — Activo comprado en Compras queda en la cuenta de activo sin alta en el auxiliar; darlo de alta después duplica la CxP o el pago

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §2, §32, §52, §53 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Cuando Compras registra una compra con naturaleza `ASSET`, Finanzas carga la cuenta de activo fijo contra Cuentas por Pagar, pero no crea el registro en el auxiliar `fixed_assets`. Ese activo existe en el mayor y no en el auxiliar: nunca se deprecia y el checklist de cierre no lo ve. La única forma de darlo de alta en el auxiliar es `CapitalizeAssetUseCase`, que exige un origen de fondos (tesorería o proveedor) y vuelve a reconocer el costo: con proveedor crea una **segunda CxP**, con tesorería registra un **segundo pago**. No existe ningún control que relacione la factura de Compras con el alta del activo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/event_handlers/finance/procurement_posting_policy.py:21-25` — `ASSET` → `asset_account_id` del perfil PURCHASE (*verificado directamente*)
- `backend/application/event_handlers/finance/procurement_payable_bridge.py:69-77` — `create_payable_in` sin `debit_nature=FIXED_ASSET` (*verificado directamente*)
- `backend/application/event_handlers/finance/procurement_payable_bridge.py:83-107` — asiento Dr activo / Cr CxP sin crear `FixedAsset` (*verificado directamente*)
- `backend/application/event_handlers/finance/procurement_immediate_payment_bridge.py:112` — misma política para compra de contado (no verificado línea a línea)
- `backend/application/use_cases/finance/capitalize_asset_use_case.py:56-59` — exige tesorería o proveedor, uno de los dos (*verificado directamente*)
- `backend/application/use_cases/finance/capitalize_asset_use_case.py:87-100` — con proveedor crea una CxP nueva `CAPEX-…` y acredita CxP otra vez (*verificado directamente*)
- `backend/application/use_cases/finance/capitalize_asset_use_case.py:102-112` — asiento Dr activo / Cr origen de fondos (*verificado directamente*)
- `backend/application/services/finance/period_close_checklist.py:108-111` — el control de depreciación solo mira `fixed_assets`
- `backend/application/services/finance/finance_bootstrap.py:269,331` — perfiles PURCHASE y FIXED_ASSET apuntan a la misma cuenta 1201

## Impacto
Finanzas y dirección. Cada compra de equipo por Compras deja un activo que no se deprecia (estados financieros sobrevaluados y gasto subestimado). Si el contador intenta corregirlo dándolo de alta en Finanzas → Activos fijos, el balance queda con el activo y el pasivo (o la salida de efectivo) **duplicados**. Riesgo de dinero: P0.

## Objetivo
- Una compra con naturaleza `ASSET` produce exactamente un reconocimiento del costo y un pasivo (o un pago), y deja el activo en el auxiliar (directa o pendiente de completar datos).
- Existe una vía para dar de alta en el auxiliar un activo **ya reconocido** por Compras, ligada al documento de origen, que no genera asiento de origen de fondos.
- Un intento de capitalizar dos veces el mismo documento de compra se rechaza o devuelve el resultado original.
- Prueba de regresión: compra ASSET → alta en auxiliar → depreciación del periodo, con balanza cuadrada y una sola CxP.
- Medición sobre una copia de la BD real: cuántas compras ASSET hay sin registro en `fixed_assets`.

## Alcance
- **Incluye:** Puentes de Compras → Finanzas para naturaleza ASSET, alta del auxiliar a partir de un documento existente, guardia de doble capitalización, medición en copia de la BD.
- **No incluye:** La solicitud de registro en el EAM (`ASSET_REGISTRATION_REQUESTED`, SDLC-ASSET-028) y la consolidación de identidades EAM/Finanzas (SDLC-ASSET-024). Corrección contable de saldos históricos (si la medición encuentra casos, va a un ítem propio).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- `docs/refactor/assets_finance_boundary_map.md` (frontera, septiembre)
- Memoria FIN-AUD d9f2bca (`FinanceCommandService` es la única vía de UI a comandos)
- SDLC-FIN-001 (handlers de compra recibida muertos, otro caso)

## Preguntas abiertas
- ¿El alta en el auxiliar debe ser automática al reconocer la CxP (con datos mínimos: vida útil por categoría) o quedar «pendiente de capitalizar» hasta que alguien complete vida útil y categoría?
- Si la medición en la copia de la BD encuentra compras ASSET ya asentadas sin auxiliar, ¿se regularizan con un alta sin origen de fondos o con un asiento de reclasificación?
