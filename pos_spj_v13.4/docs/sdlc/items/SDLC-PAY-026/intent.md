# SDLC-PAY-026 — BI atribuye toda venta mixta a su primer pago, mezcla códigos de método y no tiene dimensiones de procesador

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 10.2 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 10.2 «Reportes por método, terminal, cuenta, fecha de liquidación» (`defectuoso / ausente`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-003

## Problema
El reporte por método agrupa por `v_ventas_unificada.forma_pago`, que es el primer pago capturado de la venta: una venta de $500 pagada 200 efectivo + 300 MP aparece como $500 en efectivo. Mezcla códigos canónicos y etiquetas legacy, y el filtro `estado='completada'` deja fuera las ventas parcialmente devueltas. No hay dimensiones de terminal, cuenta cobradora ni fecha de liquidación.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/analytics/queries/bi_sales_query_service.py:46,133-137`
- `migrations/standalone/256_sales_unified_read_view.py:58-60`
- Prueba: `tests/integration/sales/test_bi_reads_unified_sales.py` (sin mixtos)

## Impacto
Gerencia ve un mix de medios de pago falso.

## Objetivo
- Reporte por método desde las asignaciones de pago, con normalización de códigos y devoluciones descontadas.
- Dimensiones terminal, cuenta MP, estación, cajero, fecha de operación y de liquidación cuando existan.
- Prueba con venta mixta y devolución parcial.

## Alcance
- **Incluye:** Consulta de BI, vista o fuente de lectura, pruebas.
- **No incluye:** Retiro del modelo `ventas` legacy (SDLC-SALES-005).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
SDLC-SALES-005, SDLC-BI-001.

## Preguntas abiertas
- Ninguna por ahora.
