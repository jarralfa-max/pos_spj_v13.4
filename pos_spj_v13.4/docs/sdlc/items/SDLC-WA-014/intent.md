# SDLC-WA-014 — Tablas del canal duplicadas y huérfanas: tres fuentes de números, dos de conversaciones, colas que nadie drena

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §75, §9, §21 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-012, SDLC-WA-013

## Problema
Conviven fuentes de verdad paralelas: números en `whatsapp_numeros`, `whatsapp_channel_numbers` y `configuraciones.wa_*`; conversaciones en `conversations.db` (`conversations`, `message_log`, `pending_intents`) y en `whatsapp_conversations`. `whatsapp_queue` y `wa_reminder_queue` no tienen escritor ni lector vivo; `wa_event_log` (creada dos veces) no tiene lector; `pedidos_whatsapp(_items)` se lee y nadie la escribe; `product_whatsapp_outbox` duplica `whatsapp_outbox`; los `.sql` 093/094 no los ejecuta el motor. Varias escrituras usan `lastrowid` sobre PK TEXT y DDL INTEGER AUTOINCREMENT en tiempo de ejecución que diverge de las migraciones.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `migrations/whatsapp_runtime.py:21,32,45-55`; `migrations/standalone/050_wa_integration.py:43,59`; `migrations/m000_base_schema.py:1059,1084,1105,2686`; `migrations/standalone/036_whatsapp_rasa.py:23`; `042_whatsapp_multicanal.py:28`; `081_wa_queue_backoff.py`
- Lectores fantasma: `backend/application/customers/queries/customer_orders_summary_query.py:49`; `customer_history_query_service.py:258`
- `backend/infrastructure/db/schema/products_schema.py:293` frente a `whatsapp_schema.py:202`
- `lastrowid`: `whatsapp_service/erp/bridge.py:492,706,771,1004`; `erp/gateways/payment_gateway.py:29`; DDL en ejecución: `erp/pos_notifier.py:230`, `state/reminder_engine.py:81`
- `migrations/093_create_delivery_core.sql`, `094_add_delivery_outbox.sql` (no ejecutados)
- Prueba: `tests/test_whatsapp_schema.py::test_every_table_has_text_primary_key` (solo tablas canónicas)

## Impacto
Datos: lo que una parte escribe, otra no lo ve; reportes y diagnósticos cuentan tablas vacías.

## Objetivo
- Documento `docs/refactor/whatsapp_schema_consolidation.md` vigente con REUSE/ALTER/MERGE/REPLACE/DROP por tabla.
- Una fuente canónica para números, conversaciones, mensajes, inbox, outbox, idempotencia, handoff, plantillas y auditoría.
- Tablas huérfanas retiradas por migración probada sobre copia de la base; sin `lastrowid` ni DDL en tiempo de ejecución.

## Alcance
- **Incluye:** Decisión por tabla y migraciones de retiro de las huérfanas sin consumidores.
- **No incluye:** Migrar los consumidores vivos (lo hacen los ítems de corte: SDLC-WA-019, SDLC-WA-022, SDLC-WA-037).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-3 (memoria); `docs/refactor/whatsapp_schema_consolidation.md` (desactualizado, SDLC-WA-051).

## Preguntas abiertas
- Ninguna por ahora.
