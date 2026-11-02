# SDLC-PAY-022 — Access Token en cada caja y en el microservicio, sin ambiente ni rotación; «Configurado» no significa conectado

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 12.1 · Fase 13.4 · Fase 18 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 12.1 «Token sólo en backend autorizado» (`defectuoso`), «Rotación / revocación» (`parcial`), «Código huérfano de credenciales» (`legacy`); 13.4 «Prueba de conexión real» (`parcial`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-001

## Problema
El token se guarda en el almacén de secretos de la máquina donde se configura (cada caja) y el microservicio usa otro desde una variable de entorno: dos fuentes que pueden divergir. No hay ambiente sandbox/producción, rotación ni revocación con llamadores. La pantalla muestra «Configurado» sólo porque el secreto existe; la prueba de conexión llama un endpoint que acepta cualquier token y no valida la cuenta ni el alcance de Point. El resolvedor de credencial y el caso de uso de ajustes de proveedor son huérfanos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/use_cases/configuracion/integration_management_use_cases.py:167-184` (*verificado directamente*), `:246-296`
- `whatsapp_service/config/settings.py:132` — `MP_ACCESS_TOKEN`
- `backend/security/secrets/encrypted_local_secret_store.py:84-97` — `rotate_secret`/`delete_secret` sin llamadores
- `backend/application/queries/configuracion/workspace_query_service.py:662-677` — Estado = existe el secreto
- `backend/infrastructure/integrations/mercadopago_credential_resolver.py:49-77` sin llamadores; `backend/application/use_cases/save_payment_provider_settings_use_case.py:10-27` depende de servicio eliminado
- Prueba: `tests/integration/configuracion/test_integration_connection_test.py:69-88` (verificador falso)

## Impacto
Exposición del token en cada equipo; configuración inconsistente entre ERP y microservicio.

## Objetivo
- El token vive sólo en el backend decidido por PAY-001, por ambiente, con rotación y revocación auditadas.
- Una sola fuente del token; el microservicio la obtiene por contrato, no por variable propia.
- «Conectado» sólo tras una verificación real de cuenta y alcance; historial de incidencias y última sincronización.
- Se retira el código huérfano con sus pruebas rotas; el instalador no instala servicios sensibles en cada caja.

## Alcance
- **Incluye:** Almacén de credenciales, pantalla de integraciones, verificación, limpieza, instalador.
- **No incluye:** Autorización backend de Integraciones (SDLC-ARQ-PERM-001); clave maestra sin pywin32 (SDLC-ARQ-INST-003).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-PERM-001, SDLC-ARQ-INST-003.

## Preguntas abiertas
- ¿Se separan instancias sandbox y producción en la misma pantalla, y quién puede cambiar de ambiente?
