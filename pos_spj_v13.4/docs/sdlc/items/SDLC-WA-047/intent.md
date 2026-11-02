# SDLC-WA-047 — 129 except Exception en el microservicio, 29 tragan el error; la taxonomía de errores del canal no existe

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §73 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
De los 23 errores de §73 solo existe uno; los demás aparecen en un docstring. Hay 129 `except Exception` fuera de pruebas y 29 que tragan el error (pass, continue o valor por defecto), varios en caminos de dinero o de mensajes.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/domain/whatsapp/exceptions.py:5-6,42`
- Tragados: `whatsapp_service/webhook/mercadopago.py:130`; `state/reminder_engine.py:100,176,205,208,331`; `erp/pos_notifier.py:309,323,342`; `ai/intent_resolver.py:33,47,138`; `erp/bridge.py:587`; `flows/pago_flow.py:122`; `flows/cotizacion_flow.py:206`; `application/confirm_order_use_case.py:177`
- Más `except Exception`: `erp/bridge.py` (21), `state/reminder_engine.py` (13), `erp/pos_notifier.py` (7)
- Prueba: ninguna

## Impacto
Fallos de dinero y de mensajes invisibles.

## Objetivo
- Errores tipados del canal; ningún `except Exception: pass` (prueba de arquitectura con ratchet).

## Alcance
- **Incluye:** Taxonomía y retiro de excepciones silenciosas en código que sobreviva al corte.
- **No incluye:** Código que se borra en SDLC-WA-050.

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
