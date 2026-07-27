# Plan de Reescritura Limpia — compras_pro.py
_Generado: 2026-05-17 | v13.4 | Fase 0_

## Objetivo

Transformar `modulos/compras_pro.py` (3 393 líneas, SQL directo, lógica mixta)
en un módulo UI puro que delega toda lógica a la capa `application/`.

Reglas absolutas durante todo el proceso:
- NO SQL directo en `compras_pro.py`
- NO widgets ocultos para compatibilidad
- NO `background:white` ni colores hardcodeados (usar `Colors.*`)
- NO PR/PO afectando inventario
- NO pestaña separada para recepción PO
- NO tocar lógica QR salvo integración mínima
- Solo 3 tabs: Compra Tradicional | Recepción con QR | Historial

---

## FASE 0 — Auditoría y documentación ✅ COMPLETADA

- [x] `compras_legacy_removal_audit.md` — inventario completo de deuda técnica
- [x] `compras_codigo_viejo_a_eliminar.md` — lista exacta de código a borrar
- [x] `compras_bugs_bloqueantes.md` — estado de todos los bugs
- [x] `compras_plan_rewrite_limpio.md` — este documento

---

## FASE 1 — Bugs bloqueantes ✅ MAYORMENTE COMPLETADA

- [x] Bug 4 (búsqueda producto foco) — `ProductSearchWidget` usa child widget
- [x] Bug 2 (proveedor abre ventana) — `QCompleter.InlineCompletion`
- [x] Bug 3 (`purchase_requests` faltante) — migración 077
- [x] Bug `peso_total_kg` — migración 076
- [ ] **Eliminar `_fallback_compra_directa`** (líneas 3353–3393) — PENDIENTE INMEDIATO

---

## FASE 2 — Extracción a repositorios

### Crear `ProveedorRepository` en `repositories/proveedor_repository.py`

Métodos a extraer de `compras_pro.py`:

```python
class ProveedorRepository:
    def get_by_id(self, prov_id: int) -> dict | None
    def search_by_nombre(self, q: str) -> list[dict]
    def get_recientes_compras(self, prov_id: int, limit: int = 5) -> list[dict]
    def get_alertas_cxp(self, prov_id: int) -> list[dict]
    def get_plantillas(self, prov_id: int, sucursal_id: int) -> list[dict]
```

### Crear `SucursalRepository.get_activas()` si no existe

SQL actual en línea 1601 (`_cargar_sucursales_compra`).

### Ajustes en `ComprasProUC` / `RegistrarCompraUC`

Verificar que `_detectar_recetas` y `_procesar_recetas` tienen cobertura en UC.

---

## FASE 3 — Rediseño completo de layout "Compra Tradicional"

### Estructura objetivo del tab

```
┌─────────────────────────────────────────────────────────────────┐
│  DocumentToolbar (folio, fecha, estado, adjunto, acciones)      │
├───────────────────────┬─────────────────────────────────────────┤
│  ProvedorPanel        │  ItemsTotalsPanel                       │
│  ──────────────       │  ─────────────────                      │
│  Buscador proveedor   │  Tabla de partidas (QTableWidget)       │
│  Info proveedor       │  ─ producto / cant / precio / subtotal  │
│  Condición pago       │  Buscador de producto (ProductSearch)   │
│  Sucursal destino     │  ─────────────────                      │
│                       │  Subtotal / IVA / Total                 │
│                       │  Forma de pago + Confirmar              │
└───────────────────────┴─────────────────────────────────────────┘
```

### Componentes a crear en `modulos/compras/`

```
modulos/compras/
├── __init__.py
├── document_toolbar.py     # QWidget: folio, fecha, estado chip, adjunto btn
├── proveedor_panel.py      # QWidget: búsqueda + info + condición pago
├── items_table.py          # QWidget: tabla partidas + buscador producto
├── totals_panel.py         # QWidget: subtotal/IVA/total + forma pago
└── purchase_form.py        # Composición de los 4 widgets anteriores
```

### Regla de responsabilidad

Cada widget recibe datos vía señales/métodos públicos.
NINGÚN widget hace SQL directamente.
`ModuloComprasPro._build_tab_tradicional()` solo instancia y conecta widgets.

---

## FASE 4 — Integración PO en pestaña QR (NO tab separada)

La pestaña "Recepción con QR" debe mostrar, después de escanear, un botón
"Recibir como PO" que invoca `RegistrarCompraUC` con los datos del paquete.

**Regla**: La lógica QR no se toca. Solo se agrega un botón en la UI de
resultados de escaneo que llama al UC existente.

**Archivos involucrados**:
- `modulos/recepcion_qr_widget.py` — agregar señal `po_recibida(compra_id)`
- `modulos/compras_pro.py:_build_tab_qr` — conectar señal al refresco de historial

---

## FASE 5 — Eliminación de código legacy

Después de que FASE 2–4 estén completas y con tests:

1. Eliminar todas las llamadas SQL directas de `compras_pro.py`
2. Reemplazar CSS hardcodeado con `Colors.*`
3. Verificar que `modulos/compras_pro.py` tenga cero llamadas `db.execute`
4. Archivar o eliminar métodos de compatibilidad migrados

---

## FASE 6 — Tests

### Tests mínimos requeridos

```
tests/test_compras_pro_layout.py       # Smoke test: widget instancia sin DB
tests/test_purchase_request_uc.py      # UC crea PR sin tocar inventario
tests/test_proveedor_repository.py     # Queries retornan dicts correctos
tests/test_registrar_compra_uc.py      # Compra actualiza inventario correctamente
```

### Criterio de completitud

- `grep -n "db\.execute" modulos/compras_pro.py` → cero resultados
- `grep -n "background:white\|color:#fff\|#F8FAFC" modulos/compras_pro.py` → cero resultados
- Todos los tests de regresión pasan
- Los 3 tabs existen y funcionan

---

## Cronograma sugerido

| Fase | Duración estimada | Bloquea |
|------|------------------|---------|
| FASE 0 | ✅ Completada | — |
| FASE 1 | 1 sesión | FASE 2 |
| FASE 2 | 2–3 sesiones | FASE 3 |
| FASE 3 | 2–3 sesiones | FASE 4 |
| FASE 4 | 1 sesión | FASE 5 |
| FASE 5 | 1 sesión | FASE 6 |
| FASE 6 | 1 sesión | — |
