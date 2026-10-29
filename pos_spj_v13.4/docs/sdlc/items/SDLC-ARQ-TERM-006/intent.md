# SDLC-ARQ-TERM-006 — Perfiles de despliegue incompletos y API móvil sin compuerta de módulo instalado

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §5 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R5.2 Perfiles de despliegue / R5.1 por API, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-001

## Problema
Los perfiles de instalación son conjuntos de capacidades (POS_ESSENTIAL / ERP_FULL / CUSTOM); no existen 'terminal administrativa' ni 'servicio local de sucursal', y nada liga el perfil al tipo de terminal. La API móvil verifica el permiso pero no la capacidad instalada (§15 T4 por API). `ApplicationContext.capabilities` vale 'todo' por defecto.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/software_distribution/install_profile.py:33-37,108-111`
- `installer/windows/spj_setup.iss:92-112`
- `backend/api/mobile_credentials.py:42`
- `backend/bootstrap/application_context.py:339`
- Pruebas: `tests/integration/software_distribution/test_profiles_and_schema_gate.py:27,40` (UI); API: ninguna.

## Impacto
Un módulo no instalado puede usarse por la API; los perfiles no reflejan los cuatro roles de despliegue del documento.

## Objetivo
- Perfiles de despliegue POS / administrativa / servicio local / central definidos y ligados al tipo de terminal.
- La API aplica la compuerta de capacidad instalada; el valor por defecto es 'nada'.
- Prueba §15 T4 por API.

## Alcance
- **Incluye:** Perfiles, compuerta en API, default seguro.
- **No incluye:** Construir el servicio local (HYB-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
