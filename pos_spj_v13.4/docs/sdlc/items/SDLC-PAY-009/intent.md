# SDLC-PAY-009 — No hay adaptador de Mercado Pago Orders API; el SDK empaquetado no se usa

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 4.2 · Fase 5 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 4 «Cliente Orders API» (`ausente`) y «SDK mercadopago» (`legacy`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-007, SDLC-PAY-022

## Problema
El backend sólo llama `GET /v1/payment_methods` para probar el token. No existe cliente para `POST /v1/orders` (Point y Checkout) con `X-Idempotency-Key` estable, ni mapeo de errores. El instalador empaqueta `mercadopago==3.6.0` y nadie lo importa; el microservicio usa `httpx` con preferencias de Checkout Pro.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/services/payment_provider_verification_service.py:7,13-34`
- `installer/windows/requirements-release.txt:39`; `requirements.txt:60`; ningún `import mercadopago`
- `whatsapp_service/flows/pago_flow.py:74-123` — `httpx` sin idempotencia

## Impacto
Sin adaptador no hay cobro integrado.

## Objetivo
- Adaptador del puerto de PAY-007 para Orders API, validado contra la documentación vigente, con clave de idempotencia derivada de la intención y reutilizada en reintentos.
- Errores y timeouts mapeados a estados internos (desconocido ≠ rechazado).
- Una sola biblioteca HTTP; se retira la dependencia no usada del instalador.
- Pruebas con servidor falso; sandbox sólo manual y documentado.

## Alcance
- **Incluye:** Adaptador, mapeo, pruebas, `requirements-release.txt`.
- **No incluye:** Terminales (PAY-012); webhooks (PAY-010).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- ¿SDK oficial `mercadopago` o `httpx` directo? SDK oficial
