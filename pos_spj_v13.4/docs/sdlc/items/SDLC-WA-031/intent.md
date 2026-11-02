# SDLC-WA-031 — El canal calcula el crédito disponible sobre clientes legacy y con eso decide si pide anticipo

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §40 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
El bridge resta `credit_limit - credit_balance` de `clientes` y con ese número decide anticipo. Existen `CheckCreditSaleEligibilityUseCase` y `CustomerCreditQueryService` en Crédito y el canal no los usa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/bridge.py:284-286,302-304,358-363,722-729`
- `backend/application/customer_credit/use_cases/check_credit_sale_eligibility_use_case.py:33`; `queries/customer_credit_query_service.py:63`
- Prueba: `tests/test_wa_bridge.py::TestGetCreditoDisponible` (no corre: error de colección)

## Impacto
Dinero: un pedido puede salir sin anticipo con crédito que no existe en el contexto dueño.

## Objetivo
- El canal consulta la elegibilidad de crédito al contexto Crédito; nunca calcula saldo ni omite anticipo por su cuenta.

## Alcance
- **Incluye:** Consulta de elegibilidad desde el canal.
- **No incluye:** Anticipos (SDLC-WA-004).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
