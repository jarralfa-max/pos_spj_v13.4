# POLÍTICA QR — NO TOCAR
> pos_spj v13.4 | Compras ERP Refactor | 2026-05-15

---

## Declaración

El motor QR de trazabilidad de contenedores es **CORE** de la operación cárnica.
Cualquier modificación no autorizada constituye un riesgo crítico de producción.

**Esta política es NO NEGOCIABLE durante las fases 0-4 del refactor.**

---

## Archivos protegidos (NO MODIFICAR lógica)

| Archivo | Motivo |
|---------|--------|
| `services/qr_service.py` | Motor de generación y escaneo QR |
| `modulos/compras_pro.py` → métodos QR | Lógica de contenedores, asignación, recepción física |
| Handlers `RECEPCION_CONFIRMADA` | Procesamiento post-recepción QR |
| Tablas `trazabilidad_qr` | Schema QR intacto |
| Tablas `movimientos_trazabilidad` | Historia QR intacta |

---

## Qué SÍ está permitido en el flujo QR

| Permitido | Descripción |
|-----------|-------------|
| UI/UX visual | Reorganizar paneles, badges, colores via ThemeManager |
| Dark/Light | Aplicar tema existente donde falte |
| Selector PO | Agregar entrada para asociar PO a contenedor en recepción |
| Visualización PO | Mostrar datos de PO en panel de asignación |
| Comparación | Mostrar esperado vs recibido contra líneas de PO |
| Estado parcial | Mostrar progreso de recepción de PO |

---

## Qué NO está permitido

| Prohibido | Razón |
|-----------|-------|
| Modificar `qr_service.py` | Motor QR — no tocar |
| Crear segundo motor QR | Duplicación |
| Crear nueva pestaña de recepción QR | Ya existe |
| Reemplazar lógica de contenedores | Riesgo de producción |
| Cambiar reglas de asignación QR | Riesgo de trazabilidad |
| Duplicar movimientos de inventario en QR | Doble inventario |
| Duplicar creación de lotes en QR | Doble kardex |
| Cambiar eventos `RECEPCION_CONFIRMADA` | Riesgo de integración |

---

## Adaptación permitida para recibir PO

Si la recepción QR necesita lógica para aceptar PO, se crea un **adaptador mínimo**:

```
application/purchases/receive_po_adapter.py
```

El adaptador:
- Lee líneas de PO desde repositorio existente
- Las expone al widget de recepción como contexto
- Compara con lo recibido físicamente
- Llama servicios existentes (NO reimplementa)
- Actualiza estado PO (PARCIAL / RECIBIDA)
- NO reemplaza ningún handler existente
- NO crea nuevos eventos de inventario

---

## Protocolo de revisión antes de tocar QR

Cualquier cambio que afecte archivos QR requiere:

1. Revisión de esta política
2. Confirmación de que es solo UI/UX o adaptador mínimo
3. Tests de no-regresión ejecutados ANTES del cambio
4. Tests de no-regresión ejecutados DESPUÉS del cambio
5. Confirmación de que `test_qr_flow_no_regression.py` sigue en verde

---

## Tests de guardia QR

Los siguientes tests deben pasar en TODO momento:

```
tests/purchases/test_qr_flow_no_regression.py
```

Incluye:
- Import del servicio QR sin error
- Generación de QR sin efectos secundarios inesperados
- Escaneo de recepción sin duplicar inventario
- Estado de contenedor correcto post-recepción
- No interferencia con flujo de Compra Tradicional

---

## Firmado

Política establecida en Fase 0 del refactor de compras.
Responsable: Arquitecto principal del ERP.
Revisión programada: Fase 6 (UI QR mejorada) — solo UI/UX.
