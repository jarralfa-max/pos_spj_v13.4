# SDLC-WA-048 — Las pruebas del canal no corren en CI: 15 fallan, 1 archivo no se recolecta y las legacy importan paquetes borrados

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §77, WA-22 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
CI corre `pos_spj_v13.4/tests/{architecture,unit,integration,ui}` y nunca `whatsapp_service/tests/` (77 archivos). Medido hoy: 699 pasan, 15 fallan y 1 archivo no se recolecta (importa `core.*`). Las 11 pruebas sueltas del ERP sobre WhatsApp (`tests/test_wa_*.py` y afines) dan 41 pasan, 15 fallan y 32 errores. Varias pruebas crean su propio esquema INTEGER AUTOINCREMENT o usan ids enteros y ocultan defectos reales (pos_notifier, adjustment_approval, bridge, selección de producto).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `.github/workflows/ci-segmented.yml:32-53,130` (raíz del repositorio)
- `python -m pytest whatsapp_service/tests -q --continue-on-collection-errors` → 15 failed, 699 passed, 1 error (2026-11-01)
- `python -m pytest tests/architecture/test_whatsapp_runtime_imports.py tests/test_wa_*.py tests/test_delivery_whatsapp_notifier.py tests/test_remediacion_c_wa_uuid.py -q` → 15 failed, 41 passed, 32 errors (2026-11-01)
- Esquemas falsos: `tests/test_wa_bridge.py:39,68-72`; `whatsapp_service/tests/test_adjustment_approval_phase7.py:42-43`; `test_pos_notifier_dedupe`
- Fallas por archivo en `arquitectura/matriz-whatsapp.md` (Mediciones)

## Impacto
Ningún cambio del canal tiene red de seguridad; las pruebas verdes certifican defectos.

## Objetivo
- Un job de CI corre `whatsapp_service/tests` y queda verde.
- Las pruebas legacy que importan código borrado se borran o se reescriben contra el código vivo.
- Las pruebas usan el esquema real de las migraciones.

## Alcance
- **Incluye:** Job de CI, saneamiento de pruebas del canal.
- **No incluye:** Guardias nuevas de §78 (SDLC-WA-049).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ORD-010 (mismo patrón en Delivery); SDLC-UI-001 (jobs de CI).

## Preguntas abiertas
- Ninguna por ahora.
