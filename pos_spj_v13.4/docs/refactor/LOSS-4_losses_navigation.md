# LOSS-4 — Sidebar y navegación de Mermas

Estado: `IMPLEMENTED_WITH_PYTEST_ENVIRONMENT_BLOCKER` (2026-08-03).

## Implementado

- Una sola entrada global `MERMAS`, sin emoji.
- `LossesView` en la estructura frontend objetivo.
- Sidebar persistente, accesible, colapsable y con ruta activa preservada.
- `QStackedWidget` con carga lazy; no se usan tabs horizontales.
- Contrato declarativo de 16 secciones y registro único de rutas.
- Permiso granular independiente por sección.
- Badges externos para pendientes, investigaciones, acciones vencidas y alertas.
- Páginas read-only con `PageHeader` y estado vacío estándar hasta sus fases funcionales.
- `LossesModuleHost` como composition root.
- Nota histórica: LOSS-5 sustituyó `_LegacyLossRegistrationBridge` por el formulario canónico.

## Secciones

```text
Resumen
Registro
Pendientes
Producción
Inventario
Caducidad y daño
Calidad y decomisos
Rendimientos
Recuperación
Disposición
Investigaciones
Acciones correctivas
Alertas
Análisis
Auditoría
Configuración
```

## Seguridad

Cada sección usa un código `LOSSES_*_VIEW`. La visibilidad es fail-closed y el permiso general `LOSSES_VIEW` no infiere acceso a secciones sensibles. Los badges no se calculan en UI.

## Validación

```text
py_compile archivos LOSS-4: PASSED
unittest navegación: 2 PASSED
pytest: BLOCKED (dependencia no instalada)
```

## Deuda temporal

Cumplido en LOSS-5: `LossRegistrationPage` reemplazó el puente y se eliminaron el bridge y el import legacy.

No se conectó ninguna escritura al schema `loss_*` durante LOSS-4.
