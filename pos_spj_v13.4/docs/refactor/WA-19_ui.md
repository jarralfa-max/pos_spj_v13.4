# WA-19 — UI (panel admin del canal WhatsApp)

Ejecutado: 2026-09-02. Continuación del batch WA-13..18 tras confirmación
del usuario (WA-19..24 pedidos; el roadmap real llega hasta WA-22 — ver
nota de alcance abajo).

## Nota de alcance

El master prompt original (81 secciones) se compactó fuera de contexto en
algún punto de esta sesión — no quedó texto §-numerado detallado para
WA-19/20/22, y WA-23/24 no aparecen en ningún roadmap registrado. Antes de
adivinar, se preguntó al usuario explícitamente: confirmó **detenerse en
WA-22** (sin WA-23/24) y **dejar WA-21 diferido** (la decisión de
eliminación de legacy sigue sin resolver, igual que desde WA-9). WA-19/20/22
se construyeron con el mejor criterio disponible, grounded en hallazgos
reales de auditorías previas (WA-0) en vez de inventar alcance — ver cada
fase para el razonamiento específico.

## Qué se construyó

WA-0 (`whatsapp_legacy_inventory.md`) ya clasificó el panel admin PyQt5
real y wireado (`modulos/whatsapp/whatsapp_module.py`, 7 tabs, usado por
`interfaz/main_window.py`) como **REUSE** — sin SQL directo, delega
correctamente a `WhatsAppAdminService`. Pero clasificó sus dos
repositorios de lectura, `WhatsAppHistoryRepository`/`WhatsAppMetricsRepository`,
como **REWRITE**, por un hallazgo concreto: ambos intentan leer
`wa_message_queue`, una **tabla fantasma** — nunca creada por ninguna
migración (confirmado por grep, otra vez, en esta fase). Cada consulta a
ella falla en silencio (`except Exception`) y cae al siguiente fallback —
funciona, pero nunca refleja el canal nuevo (WA-1..18).

WA-19 = construir UI de verdad significa, para un microservicio backend
sin frontend propio, hacer que el panel admin YA EXISTENTE y YA WIREADO
muestre datos reales del bounded context nuevo — no escribir pantallas
PyQt/web nuevas desde cero.

- `core/repositories/whatsapp_history_repository.py::_query_new_bounded_context()`
  — nueva fuente, intentada PRIMERO (antes de `wa_message_queue`/
  `bot_mensajes_log`/`pedidos_whatsapp`), leyendo
  `whatsapp_messages` ⋈ `whatsapp_conversations` ⋈ `whatsapp_identities`.
  Honesto sobre un gap real documentado desde WA-8: `whatsapp_messages`
  no persiste el texto/interactive_id crudo — la columna "mensaje" lo
  refleja (`"[TEXT] (sin texto persistido)"`) en vez de fingir contenido.
  Búsqueda limitada a número de teléfono (única columna real disponible).
- `core/repositories/whatsapp_metrics_repository.py` — `_new_bounded_context_activity()`
  (complementa `total_mensajes`/`mensajes_hoy`/`sesiones_activas` con
  datos reales del canal nuevo, solo si hay tráfico — nunca sobrescribe
  lo que ya calculó `_context_db_metrics()`) + `_new_bounded_context_operations()`
  (5 métricas genuinamente nuevas sin equivalente legacy: `wa_handoff_abiertos`,
  `wa_outbox_pendiente`, `wa_dead_letter`, `wa_entregas_solicitadas`,
  `wa_idempotencia_fallidas` — visibilidad real de WA-13..17 que el panel
  nunca tuvo).

## Bug real encontrado y corregido en el mismo pase

El primer intento de `sesiones_activas` comparaba
`last_message_at >= datetime('now','-30 minutes')` en SQL — pero
`last_message_at` se guarda vía `datetime.isoformat()` (formato
`"2026-09-02T13:15:00+00:00"`, separador `T` + offset de zona) mientras
`datetime('now', ...)` de SQLite produce `"2026-09-02 13:15:00"` (espacio,
sin zona). Comparar esos dos formatos como string no ordena
cronológicamente de forma confiable — un test propio
(`test_stale_conversation_does_not_count_as_active`, conversación de hace
2 horas) lo detectó de inmediato: el caracter `'T'` (0x54) siempre ordena
por encima de `' '` (0x20), así que CUALQUIER `last_message_at` del día de
hoy se reportaba como "activo", sin importar la hora real. Corregido
parseando con `datetime.fromisoformat()` en Python y comparando objetos
`datetime` reales — mismo criterio ya establecido en
`bootstrap/health_checks.py::check_inbox_queue` (WA-6).

## Deuda de tests preexistente, encontrada pero NO tocada

`pos_spj_v13.4/tests/test_wa_repositories.py` tiene 19/23 tests fallando
ya ANTES de esta fase (verificado con `git stash` sobre los archivos
tocados) — API completamente desalineada (`WhatsAppAdminService` no tiene
`get_bot_config`, `WhatsAppMetricsRepository.get_metrics()` nunca tuvo una
clave `"total"`/`"hoy"`, etc.). Es deuda de test abandonada de una fase
v12 anterior, no relacionada con este batch — mismo criterio que los 11
fallos preexistentes de `whatsapp_service/tests/` (`DummyParser.matcher`).
No se tocó: no es parte del alcance de WA-19 arreglar tests de un ciclo
de refactor anterior y no relacionado.

## Tests

12 tests nuevos en `tests/test_wa_admin_bounded_context_visibility.py`
(nueva fixture, monta el esquema real vía `create_whatsapp_schema()` — no
la fixture legacy-only de `test_wa_repositories.py`): historial desde el
schema nuevo, búsqueda por teléfono, estado de entrega en mensajes
salientes, degradación sin las tablas del canal, conteo de sesiones
activas/inactivas/terminales, las 5 métricas operativas nuevas.

## Siguiente fase

WA-20 (Observabilidad) — diagnóstico agregado DENTRO del propio
microservicio (`whatsapp_service/`), complementando `/health` (WA-4) con
métricas numéricas de operación, no solo HEALTHY/DEGRADED.
