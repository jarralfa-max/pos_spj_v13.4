# SDLC-ARQ-PERM-006 — Falta la matriz de permisos de los perfiles de referencia

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.8 Matriz de permisos de referencia, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-PERM-004

## Problema
El documento pide una matriz documentada para cajero, supervisor de caja, gerente, logística, compras, almacén, producción, finanzas y administración, derivada de la configuración existente. No existe; sólo hay matrices por módulo en pruebas y roles sembrados admin/gerente/cajero/almacen/repartidor/solo_lectura.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/m000_base_schema.py:3174-3181`
- `tests/unit/cash_register/test_cash_register_role_matrix.py`, `tests/unit/procurement/test_purchasing_role_matrix.py`, `tests/unit/inventory/test_inventory_role_matrix.py`

## Impacto
Sin matriz no hay base para aprobar la política de permisos ni para auditar.

## Objetivo
- `docs/` con la matriz de perfiles de análisis derivada de los catálogos y roles reales (generada por script reproducible).
- No se crean roles ni se conceden privilegios.

## Alcance
- **Incluye:** Documento + script de extracción.
- **No incluye:** Crear roles.

## Restricciones
CLAUDE.md; `docs/skills/SPJ_REFACTOR_SKILL.md`. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
