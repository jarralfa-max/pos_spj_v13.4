# LOY-26 — Antifraude

Fecha: 2026-08-31
Alcance: master prompt §29 (FraudCase), fase LOY-26.

## Un caso apunta a cualquier bounded context sin cruzar hacia él

`FraudCase.subject_id` es una referencia opaca sin validar — un caso puede señalar un `Referral`, una
`LoyaltyTransaction`, una `Membership` (todas de Fidelidad), o un cupón/vale de Instrumentos Comerciales,
o un derecho de Sorteos, y `FraudCase` nunca resuelve ni valida esa referencia contra la tabla del otro
bounded context. Mismo principio de aislamiento aplicado en cada pieza cruzada de esta sesión
(`CouponDefinition.source_program_id` en LOY-12, `LoyaltyCard.membership_id` en LOY-16,
`FraudCaseSubjectType` cubre los seis tipos posibles con un enum, sin necesidad de una tabla o FK por
cada uno).

## Segregación de funciones, otra vez el mismo patrón

Quien revisa un caso debe ser distinto de quien lo reportó (`start_review()` lo exige) — mismo patrón de
"un segundo par de ojos" ya aplicado a Programas (LOY-4), Campañas (LOY-11), Plantillas (LOY-17) y Lotes
(LOY-21) en este pipeline. Confirmar o descartar un caso siempre requiere notas de resolución explícitas
— un caso nunca se cierra en silencio.

## `OpenFraudCaseUseCase` SÍ exige permiso, a diferencia de los sweeps de sistema

A diferencia de `ExpireLoyaltyPointsUseCase`/`GrantBirthdayBenefitUseCase` (disparados por un cronómetro
o una fecha, sin actor humano real), abrir un caso de fraude es en sí mismo una acción reportable con un
actor real (un humano marcando algo como sospechoso, o un futuro detector automatizado que de todos modos
necesitaría su propia identidad de sistema) — se gatea con `FRAUD_MANAGE` como cualquier otra escritura,
sin aplicar la excepción de "nunca gatear un caso de sistema" que sí aplica a los sweeps genuinos.

## Bug real encontrado por un test preexistente, no por uno nuevo

`tests/unit/loyalty/test_loyalty_events.py::test_covers_master_prompt_62_vocabulary` (de LOY-2, la
primerísima fase de este pipeline) afirma el conjunto EXACTO de nombres de evento del catálogo de
Fidelidad. Agregar los 3 eventos nuevos de `FraudCase` lo rompió inmediatamente al correr la batería
completa — comportamiento esperado y correcto de ese test (congelar el catálogo para detectar cambios no
intencionales), no un defecto. Se actualizó el conjunto esperado agregando los 3 nombres nuevos con un
comentario explicando por qué creció. **Lección para cualquier fase futura que agregue un evento nuevo a
un catálogo ya existente**: correr la batería completa del bounded context, no solo los tests de la fase
nueva — un test de "catálogo congelado" en una fase muy anterior puede fallar por una razón legítima.

## Qué se construyó

Entidad `FraudCase` (OPEN→UNDER_REVIEW→CONFIRMED/DISMISSED). Esquema `loyalty_fraud_cases` (extiende
`create_loyalty_schema()`, migración 242, mismo patrón de extensión que 227-234), repositorio,
`LoyaltyUnitOfWork` extendido, y `backend/application/loyalty/use_cases/fraud_use_cases.py`:
`OpenFraudCaseUseCase`, `StartFraudCaseReviewUseCase`, `ConfirmFraudCaseUseCase`,
`DismissFraudCaseUseCase` — los cuatro reutilizando el permiso `FRAUD_MANAGE` ya definido en LOY-1
(`LoyaltyPermissions.FRAUD_MANAGE`/`FRAUD_VIEW`, sin necesidad de un permiso nuevo).

## Alcance honesto

- Ningún caso de uso ABRE un caso automáticamente todavía — por ejemplo, la auto-referencia ya detectada
  en LOY-10 (`SelfReferralNotAllowedError`) rechaza la operación directamente, pero no crea además un
  `FraudCase` para que quede en el registro de auditoría. Conectar detección automática → apertura de caso
  es una integración futura, no construida aquí.
- Sin página de UI para gestionar casos de fraude en `frontend/desktop/modules/fidelidad/` (la ruta
  `fidelidad.fraud` sigue siendo un marcador de posición, LOY-25).
- No hay una acción de "remediación" automática (bloquear la cuenta, anular el cupón/vale/boleto) al
  confirmar un caso — `confirm()` solo cambia el estado del caso mismo; ejecutar la remediación
  correspondiente contra el sujeto real es responsabilidad de quien llama, no de este caso de uso.

## Tests

12 tests nuevos (`test_fraud_case_domain.py`: 8; `test_fraud_use_cases.py`: 4), todos pasando. Verificado
con bootstrap real — migración 242 corre limpia. 574 tests de todo el dominio Fidelidad/Comercial/
Sorteos/Tarjetas + UI corridos juntos, sin regresión (tras actualizar el test de catálogo de LOY-2).

## Pendiente para fases futuras

- LOY-27 (Eliminación de legacy): con el rewire parcial de LOY-24 (Ventas→Sorteos) y las dos fases nuevas
  de UI (LOY-25) ya construidas, esta es la primera fase con margen real para evaluar qué legacy puede
  retirarse con seguridad — aunque, como LOY-25 documentó, el corte del menú real sigue sin hacerse.
- LOY-28 (Validación final).
