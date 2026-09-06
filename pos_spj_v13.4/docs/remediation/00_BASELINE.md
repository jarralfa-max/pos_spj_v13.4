# REMEDIATION BASELINE

Fecha: 2026-09-04. Estado observado antes de cambios de remediación.

## Branch / HEAD SHA

- Repositorio: `jarralfa-max/pos_spj_v13.4`.
- Rama: `claude/erp-financial-bounded-context-uqxz6b`.
- HEAD: `51112b59c7737480e76baedc7a83fa06c497126b`.
- Baseline original: `6e35244cfdec9ee70a3ea2ab77522a7b6f84c168`.
- `git fetch origin` completado; origin coincide con HEAD local. No se retrocedió código.
- `git status --short` sin cambios iniciales; advertencias de acceso a caches locales.

## CI actual

FAIL en configuración local: `.github/workflows/ci-segmented.yml` conserva marcadores de conflicto en líneas 35, 69 y 83. El YAML no es ejecutable. Estado remoto de GitHub Actions no verificado al levantar el baseline (`gh` no disponible); no se atribuye el resultado histórico al nuevo HEAD.

## Hallazgos P0 confirmados

| Hallazgo | Evidencia inicial | Estado |
| --- | --- | --- |
| CI inválido | `.github/workflows/ci-segmented.yml:35` | ABIERTO |
| Credencial conocida | `migrations/m000_base_schema.py:3197-3205`, `hash_password('admin123')` | ABIERTO |
| Migraciones omiten errores | `migrations/engine.py:313-318`; helpers también ocultan fallos de commit | ABIERTO |
| AppContainer productivo | `main.py:47,166` | ABIERTO |
| Shell legacy productivo | `main.py:48,191`, `interfaz/main_window.py` | ABIERTO |
| SalesService legacy | `core/services/sales_service.py:17-19,719,776,831,900` | ABIERTO |
| Dinero REAL | `migrations/m000_base_schema.py:294-295,620-622,2567` | ABIERTO |
| Relaciones funcionales enteras | `migrations/m000_base_schema.py:325-326` | ABIERTO |
| Autorización por rol | `backend/bootstrap/permission_evaluator.py:25`, `core/session_context.py:99`, `core/services/discount_guard.py:101` | ABIERTO |

## Hallazgos P1 confirmados

- Sales publica eventos síncronos dentro del SAVEPOINT y realiza publicaciones best-effort después del commit (`core/services/sales_service.py`). La existencia de un outbox en otras rutas no cierra este hallazgo.
- MainWindow y wrappers conservan composición, navegación y dependencias globales en presentación.
- Allowlists arquitectónicas todavía toleran SQL, transacciones y DDL fuera de sus límites.
- Los scanners de UI globales no cubren uniformemente `frontend/` y `ui/`.

## Hallazgos que ya no aplican / avances parciales

- La triple secuencia de bootstrap documentada en la auditoría histórica fue reemplazada en `main.py` por `backend.bootstrap.run_database_bootstrap.run_database_bootstrap_sequence`. No reconstruir las rutas anteriores.
- `DatabaseMigrationStep` ya convierte excepciones en resultado fatal y `DesktopApplicationBootstrapper` detiene pasos posteriores. Falta que el motor propague los errores.
- Ya existen `backend/security/provisioning/provision_installation_use_case.py`, `create_initial_owner_use_case.py` y `frontend/desktop/provisioning/initial_setup_wizard.py`. Debe usarse esta implementación al cerrar provisioning; no crear otro asistente paralelo.
- CompositionRoot, registros de dependencias y ApplicationShellWindow existen. Su existencia no significa cutover del runtime.
- El seed administrativo actual usa bcrypt. La documentación que lo describe como SHA256 no autenticable está desactualizada; la contraseña pública sigue siendo un bloqueo.

## Arquitecturas paralelas / legacy productivo

`main.py -> AppContainer -> MainWindow` sigue siendo el arranque real junto a infraestructura nueva de bootstrap/composición/shell. SalesService conserva flags `ALLOW_LEGACY_*` y ruta de escritura propia junto a `backend/application/sales/`. La eliminación requiere trasladar consumidores y proteger cada flujo; no basta eliminar imports en main.

## Allowlist debt

Inventario AST inicial de `tests/architecture/allowlists.py`; son tolerancias declaradas, no un conteo certificado de infracciones actuales:

| Categoría | Archivos | Contador tolerado |
| --- | ---: | ---: |
| SQL UI | 3 | 7 |
| Commit/rollback UI | 2 | 7 |
| Schema fuera de migraciones | 189 | 817 |
| Defaults numéricos | 14 | 34 |
| Teléfono plano | 3 | 11 |
| Combos de entidades | 12 | 55 |
| Rutas relativas | 18 | 35 |
| Contenedor en servicios | 16 | 24 |
| Lógica deprecated | 1 | 1 |

Hay 7 rutas en el inventario de consumidores legacy CRM. Parte del inventario schema refiere tests o schema canónico; se debe clasificar por consumidor real, sin trasladar infracciones a nuevas exclusiones.

## Orden exacto de intervención

0. Baseline con evidencia del HEAD actual (este documento).
1. Resolver semánticamente CI, conservar cobertura de ambas ramas, agregar detección global de conflictos y ejecutar compilación/checks.
2. Quitar credencial conocida y conectar provisioning canónico con protección del primer arranque.
3. Hacer fail-fast importación, contrato, ejecución, tracking y commit de migraciones; probar bloqueo de UI.
4. UUIDv7 y Money/Decimal en schema, contratos y consumidores críticos.
5. CompositionRoot como única composición productiva.
6. ApplicationShellWindow y router como único shell/navegación.
7. Cutover completo de Sales y eliminación del servicio legacy tras proteger consumidores.
8. Outbox/inbox y consumidores idempotentes cross-context.
9. RBAC, scopes y separación de funciones en backend.
10. Design System y eliminación de persistencia en presentación.
11. Eliminar consumidores, rutas, escrituras, wrappers y allowlists legacy.
12. Suite completa, auditoría estática y matriz de aceptación basada en evidencia.

## Validación y límites

Este baseline no declara cierre Enterprise ni tests aprobados. Las pruebas se registrarán por fase con comandos y resultados reales. Ninguna excepción productiva relevante equivale a PASS. La validación visual/manual y el CI remoto se reportarán por separado de pruebas locales.
