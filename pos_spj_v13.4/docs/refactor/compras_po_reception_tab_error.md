# FASE 0 — Error de pestaña separada para recepción PO

**Fecha:** 2026-05-17
**Estado:** documentado, no corregido en Fase 1.
**Fase de corrección:** Fase 2.

---

## 1. Regla estricta

Está prohibido crear pestañas llamadas o equivalentes a:

- `Recepción de PO`
- `Recepción OC`
- `PO Reception`
- `Recibir Orden`
- `Recepción PO`

La recepción de PO debe integrarse dentro de “Recepción con QR” como submodo, selector interno o panel interno.

---

## 2. Estado actual encontrado

### Nivel principal de Compras

Correcto: no existe cuarta tab externa. `ModuloComprasPro._build_ui()` crea solo:

1. `Compra Tradicional`
2. `Recepción con QR`
3. `Historial de Compras`

### Interior de Recepción con QR

Corregido: `RecepcionQRWidget._build_ui()` ya no crea `self._tab_po_recv` ni hace `addTab()` para PO. La recepción contra orden queda integrada en `📦 3. Recepcionar` mediante `self._cmb_recepcion_origen` y `self._recv_origin_stack`.

---

## 3. Riesgos mitigados

| Riesgo | Severidad | Descripción |
|---|---|---|
| Confusión UX | MITIGADO | PO se selecciona como origen dentro de la recepción física. |
| Duplicación futura | MITIGADO | No existe tab separada; el panel reutiliza el adaptador existente. |
| Doble inventario | CRÍTICO | Si PO y QR reciben por rutas distintas sin adapter único, se puede duplicar stock. |
| Doble CXP/asiento | CRÍTICO | Si recepción PO dispara finanzas fuera del flujo definido, se duplica deuda/asiento. |
| Mantenimiento | MEDIO | Contrato de tabs internas contradice el estándar del prompt. |

---

## 4. Corrección aplicada en Fase 2

Sin reescribir QR:

```text
Recepción con QR
└── Panel Origen
    ├── QR / Contenedor
    ├── Orden de Compra / PO
    └── Transferencia (si existe)
```

Pasos aplicados:

1. Se mantuvieron las cuatro tabs QR existentes.
2. Se movió el contenido útil de recepción contra PO a `_build_po_reception_panel()`.
3. Se reutiliza `receive_po_adapter`; no se agregó motor de inventario nuevo.
4. Los tests de Fase 2 ahora exigen cuatro tabs internas y ausencia de `_tab_po_recv`.

---

## 5. Criterio de aceptación Fase 2

- No hay tab externa PO.
- No hay tab interna llamada `Recepción PO`/`PO Reception`/similar.
- Sí hay selector/panel de origen PO dentro de “Recepción con QR”.
- QR/contenedor conserva comportamiento actual.


## Actualización 2026-05-17 — guard anti-regresión

Se agregó un fail-safe en `ModuloComprasPro` y `RecepcionQRWidget` que elimina cualquier pestaña accidental cuyo título normalizado coincida con `Recepción PO`, `Recepción de PO`, `PO Reception`, `Recepción OC` o `Recibir Orden`. La recepción contra PO sigue siendo únicamente un submodo dentro de `📦 3. Recepcionar`; no se tocó el motor QR ni se creó una ruta paralela.

## Actualización Fase 8 — selector de origen completo

El selector interno de `📦 3. Recepcionar` ahora incluye QR, PO y Transferencia. Transferencia queda como opción reservada/informativa dentro del mismo stack para no crear pestañas ni duplicar inventario/kardex del módulo Transferencias.
