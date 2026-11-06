# SDLC-ASSET-029 — No existe autorización en caliente en Activos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §85 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011

## Problema
§85 pide autorización de un segundo, sin PIN local, para baja, pérdida, robo, capitalización sensible, cambio extraordinario de ubicación, override de inspección, cierre de OT crítica y reimpresión de etiqueta. Solo hay un método sin uso que no reutiliza el verificador común de autorizador de Seguridad.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/assets/authorization.py:72-83`
- `backend/application/security/authorizer_permission_checker.py` — verificador común existente

## Impacto
Operaciones sensibles sin segundo autorizador.

## Objetivo
- Autorización en caliente sobre el verificador común (identidad y permiso del autorizador verificados en backend), auditada.
- Pruebas.

## Alcance
- **Incluye:** Mecanismo y aplicación a las operaciones de §85 que ya existan.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- Memoria ERP Fase 5: `AuthorizerPermissionChecker` vive en security (estándar único)
- SDLC-SEC-002 (autorización de dos personas confía en IDs de la UI)

## Preguntas abiertas
- Ninguna por ahora.
