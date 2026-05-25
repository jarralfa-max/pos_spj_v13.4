# Arquitectura final (Fases 1–10)

## 1) Separación de responsabilidades

- **UI (`modulos/*`)**: captura inputs, renderiza estados y mensajes de negocio.
- **Application services**: orquestación de casos de uso (p. ej. producción por lote).
- **Domain/services (`core/services/*`)**: reglas de negocio, validaciones y resolución de movimientos.
- **Repositories (`repositories/*`)**: persistencia y reglas de acceso a datos.
- **Eventos (`core/events/*`)**: integración desacoplada inventario/costos/finanzas/auditoría.

## 2) Producción

- **Producción teórica por receta**: `RecipeEngine` calcula movimientos esperados y validaciones.
- **Producción cárnica real por lote**: `ProductionApplicationService` con flujo:
  1. `abrir_lote`
  2. `agregar_subproducto`
  3. `preview_lote`
  4. `cerrar_lote`
- El cierre de lote concentra la actualización atómica de inventario, merma y costos.

## 3) Recetas

- `tipo_receta` normalizado en forma canónica (subproducto/combinacion/produccion).
- Validación por tipo:
  - **SUBPRODUCTO**: rendimiento + merma = 100.
  - **COMBINACION/PRODUCCION**: cantidades positivas; sin obligación de 100%.
- Componentes con metadatos: `cantidad`, `unidad`, `component_role`, `factor_costo`.

## 4) Ventas compuestas y virtuales

- `SalesService` resuelve líneas con `SaleFulfillmentService` en modos:
  - `DIRECT`
  - `COMPOSITE`
  - `VIRTUAL_FROM_COMPONENTS`
- El payload de `SALE_ITEMS_PROCESS` incluye trazabilidad mínima:
  - producto vendido,
  - modo de fulfillment,
  - producto origen,
  - componentes descontados finales.

## 5) Costeo

- Costeo fuera de UI y centralizado en `ProductionCostService`.
- Distribución soportada por peso/factor y tratamiento de merma (absorbida o separada por configuración).
- Persistencia de trazabilidad en `production_cost_ledger` para reconstrucción posterior.

## 6) Reglas de robustez (Fase 10)

- Evitar `except: pass` en rutas críticas de venta/producción.
- Eventos críticos sin payload útil o con fallos silenciosos deben registrar error y/o abortar operación crítica.
- No duplicar descuentos de inventario/costeo: la deducción y el costeo se ejecutan por un único flujo orquestado.
