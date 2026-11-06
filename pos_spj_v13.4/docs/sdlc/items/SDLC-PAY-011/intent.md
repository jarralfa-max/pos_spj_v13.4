# SDLC-PAY-011 — Sin conciliación por consulta: un pago con webhook perdido, timeout o reinicio queda sin resolver

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 4.4 · Fase 7 · Fase 8.2 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 7 «Reconciliación por consulta sin webhook» (`ausente`), Fase 13 «Recuperar cobro pendiente tras reinicio» (`parcial`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-007, SDLC-PAY-009

## Problema
No existe tarea que consulte intenciones pendientes o inciertas. Si la respuesta de creación se pierde, el POS se reinicia o el webhook nunca llega, nada recupera el estado sin volver a cobrar. La campana de notificaciones no tiene escritor para avisos de pago.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/flows/pago_flow.py:67-72` — `PAGO_ESPERANDO` sólo responde «espera»
- `frontend/desktop/modules/sales_pos/sales_pos_workspace.py:239-257,546-552` — aviso de cobro pendiente sin consulta al proveedor
- `backend/application/notifications/user_inbox_service.py:19-39` — sólo lectura
- Prueba: ninguna

## Impacto
Riesgo de doble cobro al cliente o de ventas perdidas tras cortes de red.

## Objetivo
- Tarea periódica y bajo demanda («recuperar estado») que consulta intenciones `esperando`/`desconocida` con la misma clave lógica.
- Nunca crea un cobro nuevo automáticamente; resultados tardíos se aplican una sola vez.
- Aviso in-app al resolver un pago tardío.
- Pruebas: respuesta perdida, reinicio del POS, webhook nunca recibido.

## Alcance
- **Incluye:** Servicio de conciliación, programación, notificador, pruebas.
- **No incluye:** Conciliación de liquidaciones (PAY-019).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
