# SDLC-WA-013 — Pedidos por WhatsApp caen en la sucursal 1 cuando falta sucursal y todo sale por un solo número

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §10, §11 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Con `ctx.sucursal_id or 1` el pedido, su clave de idempotencia, el horario y el registro de cliente toman una sucursal 1 inventada (ids reales son UUIDv7). El envío ignora la sucursal y usa un token y número globales. El registro de números vivo lee la tabla legacy `whatsapp_numeros` (dos DDL distintos; `alertas` se mapea a VENTAS), mientras `whatsapp_channel_numbers` no tiene forma de darse de alta. El buscador de productos por texto libre se construye con sucursal vacía y nunca se ajusta, así que tarifica solo con lista base y stock 0. No existen políticas de enrutamiento entrante ni saliente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/flows/pedido_flow.py:270,279,301`; `flows/registro_flow.py:85`; `router/message_router.py:144-145`; `erp/bridge.py:845`; `erp/business_orchestrator.py:51`; `erp/adjustment_approval.py:130,140`; `erp/pos_notifier.py:237`; `state/reminder_engine.py:52,88,155`
- `whatsapp_service/messaging/sender.py:44-50` — un solo token y número
- `whatsapp_service/config/numbers.py:53-62,75-76,93` — tabla legacy; registro vacío si falla la carga
- `whatsapp_service/main.py:131` — `ProductMatcher(erp.db, sucursal_id="")`; `set_sucursal` sin llamadores *(verificado directamente)*
- Canon sin uso: `whatsapp_service/domain/whatsapp/entities/channel_number.py:20-75`; `backend/infrastructure/db/schema/whatsapp_schema.py:102`
- Prueba: `whatsapp_service/tests/test_message_router_branch_switch.py::test_global_number_allows_branch_change_command`; nada cubre el valor por defecto

## Impacto
Operación multi-sucursal: pedidos asignados a una sucursal inexistente o equivocada; precio y existencia incorrectos en texto libre; no se puede tener un número por sucursal.

## Objetivo
- Ningún `or 1` ni sucursal inventada en el canal; sin sucursal resuelta el flujo la pide o queda pendiente.
- Número receptor → cuenta → sucursal → rol de canal resuelto por política; número global resuelve por cliente, dirección o elección explícita.
- El envío sale por el número de la sucursal o rol que corresponda.
- El buscador de productos usa la sucursal de la conversación.

## Alcance
- **Incluye:** Políticas de enrutamiento, registro de números canónico en el camino vivo, sucursal del buscador.
- **No incluye:** Pantalla de alta de números (SDLC-WA-043).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-2 (memoria).

## Preguntas abiertas
- Con número global: ¿la sucursal se toma de la última compra del cliente, de su dirección, o se le pregunta siempre?
