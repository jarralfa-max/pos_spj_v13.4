# SDLC-WA-049 — Ninguna de las 20 guardias de arquitectura del canal existe y la única que hay falla

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §77, §78 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-048

## Problema
No existe ninguna de las 20 guardias de §78 (un solo webhook, un solo sender, una sola outbox, sin escritura a tablas del ERP, sin cálculos en flujos, UUIDv7, normalización canónica, secretos en almacén, main mínimo, sin `sys.path`, plantillas no fijas, IA sin comandos, consentimiento, sin legacy, allowlist vacía). La guardia de imports existente falla y solo mira el momento de importación, no el `sys.path` en ejecución.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `tests/architecture/test_whatsapp_runtime_imports.py::test_channel_uses_qualified_imports` — FALLA (medido 2026-11-01)
- Equivalentes parciales: `tests/architecture/test_clean_birth_guardrails.py:679,788`; `whatsapp_service/tests/test_sender_consent_gate.py`; `test_redaction.py`

## Impacto
Sin guardias, el legacy vuelve a entrar en cada cambio.

## Objetivo
- Las 20 guardias existen, corren en CI y arrancan con una allowlist explícita que solo puede decrecer (ratchet).

## Alcance
- **Incluye:** Guardias y allowlist inicial.
- **No incluye:** Vaciar la allowlist (SDLC-WA-050).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
