# SDLC-PROC-004 — Salidas de despiece estimadas sin regla de venta, pesaje posterior ni conciliación

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `inputs/correcciones.md` C-06 (oleada 3); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P1 — Rendimiento estimado y calidad requieren política para venta y conciliación» y §4 (ejemplo de 100 kg)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PROC-001

## Problema
El diálogo de transformación directa permite rellenar las salidas vacías con lo esperado por el perfil de rendimiento; esas salidas se registran como `ESTIMATED` y mueven inventario con los kg estimados. No hay regla de si ese saldo estimado se puede vender, con qué tolerancia, ni un pesaje posterior que concilie lo estimado contra lo real con movimientos compensatorios.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `frontend/desktop/modules/meat_processing/dialogs_direct_transformation.py:62-73` — botón «Usar lo esperado en las vacías» y motivo del estimado.
- `backend/application/meat_processing/use_cases/order_execution_use_cases.py:505` — `"weight_source": ("ESTIMATED" if r.product_id in p.get("estimated", ()) ...)`.
- **No verificado:** si Ventas distingue hoy saldo `ESTIMATED` de pesado al reservar/cobrar (no se encontró regla; se confirmará en Design).

## Impacto
Inventario y costo de cortes pueden diferir del real sin rastro de ajuste; ventas de saldo que físicamente no existe.

## Objetivo
- Venta de saldo estimado solo si la configuración lo permite y dentro de la tolerancia definida.
- Pesaje posterior por lote/corte que genera movimientos compensatorios auditados sin sobrescribir la genealogía original.

## Alcance
- **Incluye:** política de venta de estimados, pesaje posterior, conciliación y su rastro.
- **No incluye:** coordinador recepción → transformación (SDLC-PROC-001); reconstrucción virtual del entero (pregunta abierta global, sin ítem).

## Restricciones
CLAUDE.md reglas 11-13 (diferencias de valuación con asiento balanceado vía `finance_service.registrar_asiento()`); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO; migraciones probadas sobre copia de la BD; presupuesto $0; Windows. Nivel T0 (mueve inventario): spec aprobado por escrito, regresión antes del cambio, revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria PROC-AUD 32cfbf (pesos estimados introducidos con la migración 343); SDLC-PROC-003 (asiento de costo fallido).

## Preguntas abiertas
- ¿Se permite vender cortes estimados antes de pesarlos? si · bloquea `/sdlc-design SDLC-PROC-004`
- Si se permite, ¿con qué tolerancia (porcentaje por corte, por lote o global) y quién la configura? se configura en el perfil del prodcto · bloquea `/sdlc-design SDLC-PROC-004`
