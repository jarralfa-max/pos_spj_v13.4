# SDLC-UI-013 — El indicador de sesión siempre dice 'Conectado': offline_status nunca cambia y 'próxima a vencer' no tiene fuente

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §26, §20 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-SYNC-005, SDLC-ARQ-HYB-002, SDLC-ARQ-SESS-002

## Problema
La barra superior y la barra de estado dibujan bien los estados Conectado, Sin conexión, Conexión limitada, Sesión bloqueada y Próxima a vencer, con texto y no solo color. Pero la fuente es falsa: `offline_status` vale `ONLINE` por defecto y nada en producción lo cambia, y el estado de replicación nunca llega al contexto. Tampoco hay quien produzca «bloqueada» ni «próxima a vencer», aunque la sesión tiene TTL y `expires_at`. La barra de estado no muestra versión ni operaciones pendientes de sincronizar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `backend/bootstrap/application_context.py:111` (`offline_status='ONLINE'`; la única otra asignación, `:152`, es una copia)
- `replication_repository.py:35,65` (estado ONLINE/OFFLINE de sync no conectado; ruta exacta **no verificada**)
- `frontend/desktop/shell/application_shell/top_bar.py:142,150-164`; `status_bar.py:52-53`
- `backend/security/sessions/session_manager.py:23,62,81` (TTL y `expires_at` sin lector en la UI)
- `tests/ui/shell/test_user_session_controls.py:95,114` (solo fijan el estado a mano)

## Impacto
Cajero y gerente creen estar conectados cuando la estación no replica; un indicador que siempre dice lo mismo enseña a ignorarlo.

## Objetivo
- El estado de conexión viene de una señal real (servicio de replicación o salud del central) y se actualiza en vivo
- «Próxima a vencer» y «Bloqueada» se producen desde el gestor de sesión
- La barra de estado muestra versión y pendientes de sincronizar
- Prueba de integración: al cortar la señal, la UI muestra «Sin conexión»

## Alcance
- **Incluye:** Contexto de la aplicación, TopBar y StatusBar; lectura del estado de sync.
- **No incluye:** Implementar la replicación (SDLC-SYNC-005) o el bloqueo (SDLC-ARQ-SESS-002).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
SDLC-SYNC-005 (ninguna estación replica todavía), SDLC-ARQ-HYB-002 (estado offline nunca se fija), SDLC-ARQ-SESS-002 (sin bloqueo ni expiración).

## Preguntas abiertas
- Mientras no exista replicación (SDLC-SYNC-005), ¿el indicador debe ocultarse o decir «Sin sincronización configurada»? Sin Sincronizacion configurada
