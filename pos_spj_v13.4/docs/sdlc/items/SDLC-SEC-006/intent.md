# SDLC-SEC-006 — Filtro de redacción de secretos no instalado en el logging y sin patrón para tokens Bearer

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 12.1 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 12.1 «Secretos fuera de logs» (`defectuoso`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** —

## Problema
Existe `SensitiveDataRedactionFilter`, pero ningún handler de logging lo instala, y su patrón no enmascara `Bearer <token>` en texto libre. Hoy ningún camino de pagos registra el token, pero no hay red de seguridad para cuando el adaptador HTTP registre peticiones o errores.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/audit/sensitive_data_redaction.py:71`
- Auditoría de Configuración sí usa `redact_mapping` (`frontend/desktop/modules/configuracion/configuracion_presenter.py:342-343`)
- Prueba: sólo unitaria del filtro

## Impacto
Riesgo de filtrar Access Tokens en archivos de log de cada equipo.

## Objetivo
- El filtro se instala en la configuración de logging de la app, la API y el microservicio.
- Enmascara `Bearer`, `access_token`, `APP_USR-`/`TEST-` y cabeceras de firma.
- Prueba: un log con token sale enmascarado.

## Alcance
- **Incluye:** Configuración de logging, filtro, pruebas.
- **No incluye:** —

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SEC-005 (endurecimiento menor).

## Preguntas abiertas
- Ninguna por ahora.
