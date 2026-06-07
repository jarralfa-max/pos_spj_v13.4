# MERMA — Fase 11: arquitectura y separación de responsabilidades

## Alcance

Esta auditoría documenta el estado arquitectónico del módulo MERMA después de las fases 1 a 10. No introduce un refactor funcional masivo; define límites, deuda y una ruta segura para continuar sin romper el flujo actual.

## Reglas del refactor aplicadas

- La operación crítica **Registrar merma** debe pasar por la ruta canónica `RegisterWasteUseCase`.
- La UI PyQt debe capturar datos, mostrar validaciones y llamar casos de uso; no debe ejecutar SQL ni hacer `commit()`/`rollback()`.
- Las lecturas para la UI deben pasar por `WasteQueryService`.
- Las escrituras y transacciones deben quedar detrás de `WasteApplicationService` y `WasteRepository`.
- Los cambios de schema pertenecen exclusivamente a `migrations/`.
- Las mutaciones críticas deben tener `operation_id` y evento de dominio.

## Ruta canónica actual

```text
ModuloMerma (PyQt)
  ├─ SearchSelector -> WasteQueryService.search_products()
  ├─ RegisterWasteCommand
  └─ RegisterWasteUseCase
       └─ WasteApplicationService
            ├─ WasteRepository.register_waste()
            ├─ WasteRepository.decrease_inventory_for_waste()
            ├─ WasteRepository.save_changes()/rollback_changes()
            ├─ WasteFinanceHandler.record_loss()
            └─ EventBus.publish(WASTE_REGISTERED)
```

## Separación actual por capa

| Responsabilidad | Dueño actual | Estado |
| --- | --- | --- |
| Captura de cantidad, motivo, notas, fecha | `ModuloMerma` | Correcto para UI |
| Búsqueda y selección de producto | `SearchSelector` + `WasteQueryService` + `WasteRepository` | Parcialmente correcto; la UI aún mantiene cache para selección |
| Validación visual de producto/cantidad/stock alto | `ModuloMerma` | Aceptable temporalmente; debe moverse a policy/service si crece |
| Permiso `MERMA.crear` | `ModuloMerma` + `core.permissions` | Deuda: permiso aún está en UI |
| PIN de alto valor | `ModuloMerma` + `DiscountGuard` | Deuda alta: autorización debe moverse a un application/domain service |
| Registro de merma | `RegisterWasteUseCase` + `WasteApplicationService` | Correcto |
| SQL de merma, historial e inventario | `WasteRepository` | Correcto para fase actual |
| Transacción crítica | `WasteApplicationService` + `WasteRepository` | Mejorado; insert + inventario + commit/rollback quedan juntos |
| Finanzas por merma | `WasteFinanceHandler` | Correcto como adaptador, pero falta handler/evento persistente más robusto |
| Evento `WASTE_REGISTERED` | `WasteApplicationService` + `EventBus` | Correcto, con deuda de outbox persistente |
| Auditoría UI (`auto_audit`) | `ModuloMerma` | Deuda media: duplica parcialmente evento/resultado |
| Migraciones / índices / columnas | `migrations/standalone/097_waste_schema_integrity.py` | Correcto |

## Qué está mezclado todavía

### En `ModuloMerma`

- Construcción manual de dependencias backend desde `container.db`.
- Validación de permisos y PIN de gerente.
- Validaciones de negocio de stock alto/valor alto.
- Auditoría con `auto_audit` después del caso de uso.
- Mensajes de UI y decisiones de confirmación.

Esta mezcla es tolerada temporalmente porque el módulo ya quedó protegido por pruebas y la mutación principal no se ejecuta en la UI. No debe ampliarse.

### En `WasteApplicationService`

- Coordina persistencia, inventario, finanzas y evento.
- Esto es aceptable para la fase actual, pero a mediano plazo finanzas/eventos deberían ejecutarse por handlers idempotentes u outbox para reducir acoplamiento temporal.

### En `WasteRepository`

- Contiene SQL de merma e inventario branch-aware.
- Es aceptable como infraestructura, pero la decisión de qué fuente de inventario es canónica debe moverse a un `InventoryApplicationService` o `UnifiedInventoryService` cuando exista una ruta estable para MERMA.

## Cambios aplicados hasta esta fase

- La UI ya no registra merma directamente ni ejecuta SQL.
- La búsqueda usa `WasteQueryService` y `SearchSelector`.
- El registro usa `RegisterWasteUseCase` y `WasteApplicationService`.
- La persistencia crítica tiene rollback en fallo.
- Finanzas y EventBus son side effects no fatales después de persistir.
- El schema requerido queda protegido por migración idempotente.

## Cambios NO aplicados en Fase 11

- No se movió la autorización/PIN fuera de UI para no cambiar flujo funcional sin más pruebas.
- No se sustituyó el repositorio por un `InventoryService` porque aún hay rutas legacy con `productos.existencia`, `inventario_actual` y `branch_inventory`.
- No se creó outbox persistente para eventos de merma; requiere diseño transversal con EventBus.
- No se eliminó `auto_audit`; requiere decidir si auditoría debe derivarse de evento, outbox o tabla específica.

## Riesgos pendientes

| Severidad | Riesgo | Impacto |
| --- | --- | --- |
| Alta | Autorización PIN y permisos siguen en UI | Difícil reutilizar desde API futura y riesgo de duplicar reglas |
| Alta | EventBus en memoria no garantiza entrega | Reportes/notificaciones pueden perder eventos si falla handler/proceso |
| Media | Auditoría UI puede duplicar o divergir del evento `WASTE_REGISTERED` | Trazabilidad fragmentada |
| Media | Inventario branch-aware aún usa fallback global `productos.existencia` | Riesgo de confusión si sucursal y global divergen |
| Media | Finanzas se ejecuta como side effect directo | Puede requerir reconciliación si falla después del commit |
| Baja | `ModuloMerma` construye servicios con `container.db` | Acoplamiento desktop/container; aceptado temporalmente |

## Plan recomendado por fases

1. **Fase 12 — Logging y diagnóstico:** consolidar logs `[MERMA]`/`[WASTE]` y documentar correlación por `operation_id`.
2. **Fase 13 — Pruebas:** ampliar smoke tests de `ModuloMerma` con container mock y pruebas de permisos/PIN sin abrir diálogos reales.
3. **Fase 14 — Manual QA:** ejecutar checklist GUI real en entorno con PyQt completo.
4. **Fase 15+ — Refactor seguro:** extraer `WasteAuthorizationService` para permisos/PIN y `WasteAuditHandler`/outbox para auditoría derivada de eventos.
5. **Inventario futuro:** conectar MERMA a un servicio canónico de inventario por sucursal cuando la ruta oficial esté definida y cubierta.

## Decisión arquitectónica de esta fase

No se modifica código funcional en Fase 11. La fase deja documentada la frontera actual, evita refactor masivo y establece el backlog técnico requerido para que MERMA termine siendo principalmente UI + UseCase, con lógica de negocio y side effects fuera de PyQt.
