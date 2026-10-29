# SDLC-ARQ-HYB-001 — No existe servicio local de sucursal: caja, turno e inventario no pueden coordinarse entre terminales

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §2 · §9 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R2.C / R9.2 Servicio local de sucursal, estado `documentado no implementado`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-001, SDLC-ARQ-SHIFT-001, SDLC-ARQ-SHIFT-004

## Problema
El documento pide un servicio local de sucursal en una PC Windows que coordine recursos compartidos sin internet. Cada terminal tiene su propia SQLite con candado exclusivo, y la auditoría de fase 0 decidió 'cajas autónomas' (D1/N07). `backend/api/service_host.py` es sólo la API móvil de Logística. Dos terminales pueden abrir turno en la misma caja/cajón y nadie lo detecta, ni local ni centralmente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/shared/app_paths.py:140-149`; `frontend/desktop/app.py:79,113-138`; `backend/infrastructure/runtime/instance_lock.py:1-10`
- `docs/architecture/enterprise_org/00_phase0_audit.md:42,147` (N07, D1 = cajas autónomas)
- `backend/api/service_host.py:1-31,41-47,150-155`
- `backend/application/cash_register/shift_use_cases.py:78`; `backend/infrastructure/central/projection_repository.py:108-115`
- Pruebas: ninguna (§15 T6, T7).

## Impacto
Bloquea la operación multi-terminal por sucursal pedida por el documento: caja compartida, turno compartido, inventario coherente entre cajas sin internet.

## Objetivo
- Decisión aprobada que reemplace o confirme D1, registrada como ADR.
- Si se aprueba: servicio local mínimo (FastAPI) que sea autoridad de turno/caja en la sucursal, con protocolo versionado, autenticación de terminal y pruebas con dos terminales (§15 T6, T7).
- Evaluación documentada de la PC anfitriona (respaldo, disponibilidad, seguridad).

## Alcance
- **Incluye:** ADR + primer slice: autoridad local de turno/caja.
- **No incluye:** Inventario compartido (slice posterior), operación degradada (HYB-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Decisión D1 de `docs/architecture/enterprise_org/00_phase0_audit.md`; `docs/sdlc/PLAN-MAESTRO.md` (PC anfitriona 24/7 para webhooks).

## Preguntas abiertas
- El documento de requisitos (§2.C, §9) contradice la decisión D1 'cajas autónomas'. ¿Cuál prevalece?
- ¿Qué PC de la sucursal aloja el servicio local y qué pasa si se apaga?
