# Política Fase 0/Fase 1 — No tocar motor QR

**Fecha:** 2026-05-17
**Aplica a:** `modulos/recepcion_qr_widget.py`, servicios QR existentes y cualquier flujo de contenedor/recepción actual.

---

## 1. Regla operativa

Durante Fase 0 y Fase 1:

- No se modifica `RecepcionQRWidget`.
- No se cambia parsing QR.
- No se cambia generación de etiquetas.
- No se cambia asignación de compra a contenedor.
- No se cambia recepción de contenedor.
- No se cambia historial QR.
- No se cambia inventario/kardex/lotes usados por el motor QR.

---

## 2. Decisión Fase 2

`RecepcionQRWidget` ya no contiene una pestaña interna llamada `🧾 Recepción PO`. La recepción contra orden se integró como submodo dentro de la pestaña `📦 3. Recepcionar`, mediante selector de origen. La lógica QR de generación, asignación, recepción de contenedor e historial se conserva.

---

## 3. Integración PO permitida en fases futuras

La recepción PO debe vivir dentro de “Recepción con QR” como:

```text
Recepción con QR
├── Origen: QR / Contenedor
├── Origen: Orden de Compra / PO
└── Origen: Transferencia (si existe soporte)
```

Implementación futura preferida:

1. Mantener `RecepcionQRWidget` como contenedor de recepción física.
2. Usar el selector interno `Origen de recepción` para alternar `QR / Contenedor` y `Orden de Compra / PO`.
3. Reutilizar `receive_po_adapter` para la recepción PO existente.
4. Evitar SQL nuevo en widgets.
5. Evitar duplicar lógica de recepción, inventario, kardex, lotes, CXP, asientos o eventos.

---

## 4. Tests de protección en Fase 1

Los smoke tests de Fase 1 deben comprobar:

- El módulo importa.
- Compras tiene exactamente tres tabs principales.
- No existe tab principal de recepción PO.
- `RecepcionQRWidget` sigue importable.
- No existe tab interna o externa de recepción PO; PO vive como submodo/panel dentro de `Recepcionar`.
