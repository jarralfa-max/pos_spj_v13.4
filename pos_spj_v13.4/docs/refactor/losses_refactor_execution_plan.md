# LOSS-0 — Plan de ejecución del bounded context Losses

Estado: `LOSS-2 IMPLEMENTED_WITH_TEST_ENVIRONMENT_BLOCKER`. El dominio base,
clasificaciones, causas, estados, policies y eventos están implementados y
compilados. Antes de LOSS-3 debe ejecutarse pytest; el entorno actual no contiene
esa dependencia.

## Brechas bloqueantes

1. Dos mutaciones y dos tablas representan pérdidas.
2. No existen `backend/domain/losses/` ni `LossCase`.
3. Motivos, umbral y estados están hardcodeados/ausentes.
4. Se usa `float`/`REAL` en cantidades, pesos, costos y porcentajes.
5. Autorización, cálculo y auditoría permanecen en PyQt.
6. Se publican eventos legacy junto al canónico.
7. No hay outbox transaccional común.
8. No existen frontend objetivo, sidebar ni páginas requeridas.
9. Faltan evidencia, disposición, recuperación, investigación, causa raíz y correctivas.
10. La ruta visible no modela almacén consistentemente.

## Reglas a preservar con characterization tests

- Una pérdida física no deja inventario negativo.
- Un reintento no duplica expediente ni movimiento.
- El scope por sucursal no afecta otras sucursales.
- Solo Inventario modifica stock físico.
- Merma teórica no genera salida.
- Caducidad/disposición/decomiso requieren autorización.
- Coproducto/subproducto aprovechable no es merma automática.
- El costo queda como snapshot auditable.

## Secuencia y gates

| Fase | Resultado | Gate |
| --- | --- | --- |
| LOSS-1 | Seguridad granular, scopes, límites, segregación y hot auth | Tests backend de autorización |
| LOSS-2 | Dominio, policies y eventos UUIDv7/Decimal | Unit tests de invariantes |
| LOSS-3 | Schema `loss_*`, outbox e idempotencia born-clean | Bootstrap + FK check |
| LOSS-4 | Entrada `MERMAS` y sidebar persistente | Tests de rutas/permisos |
| LOSS-5 | Draft/submit con líneas, lote, cantidad/peso y evidencia | UI/application tests |
| LOSS-6 | Solicitud/confirmación/reverso de Inventario | Sin escritura directa/doble |
| LOSS-7–12 | Producción, carne, yield, expiry, calidad y transferencias | Contract tests |
| LOSS-13–17 | Recuperación, disposición, investigación y correctivas | Workflow/idempotencia |
| LOSS-18–20 | Costos/Finanzas, notificaciones/WhatsApp y BI | Eventos post-commit/queries |
| LOSS-21–22 | UI/UX completa y offline | Arquitectura/accesibilidad/sync |
| LOSS-23 | Eliminación legacy y allowlist vacía | Suite completa/cero consumidores |
| LOSS-24 | Auditorías y validación manual | `MIGRATED` |

## Siguiente corte recomendado: LOSS-1

1. Caracterizar permisos actuales y ambas rutas de registro.
2. Definir permisos granulares sin convertir `MERMA` en permiso final.
3. Crear puertos de autorización con actor, sucursal, almacén, importe y clasificación.
4. Revalidar en backend; la UI solo solicita.
5. Mantener la ruta actual hasta paridad de LOSS-2/LOSS-3.

Tests prioritarios: detectar doble ruta; identidad de entidad distinta de `operation_id`; Decimal-only; evento único; cero escritura Losses→Inventario/Finanzas; autorización/scopes; coproducto no clasificado como pérdida.

## Riesgos

| Riesgo | Severidad | Mitigación |
| --- | --- | --- |
| Doble baja al unir rutas | Crítica | Un puerto de posting + constraint/test idempotente |
| Confundir entidad y operación | Crítica | UUID independientes generados en aplicación |
| Contabilización perdida/duplicada | Alta | Outbox + consumidor idempotente |
| Eliminar ajustes no relacionados | Alta | Inventario de consumidores antes de LOSS-23 |
| Revaluación histórica | Alta | Snapshot Decimal por línea |
| Permiso solo UI | Alta | Revalidación backend y auditoría |

## Validación LOSS-0

```text
python -m pytest tests/architecture/test_merma_guardrails.py
python -m pytest tests/architecture/test_merma_no_legacy_permissions.py
python -m pytest tests/architecture/test_waste_module_refactor.py
python -m pytest tests/architecture/test_waste_uuid_identity.py
python -m pytest tests/unit/test_waste_refactor.py
python -m pytest tests/integration/test_waste_repo_uuid_identity.py
python -m pytest tests/integration/inventory/test_inventory_waste.py
python -m pytest tests/integration/inventory/test_waste_canonical_adapter.py
```

LOSS-0 no resetea DB, abre GUI ni elimina legacy.
