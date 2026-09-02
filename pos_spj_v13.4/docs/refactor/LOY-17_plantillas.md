# LOY-17 — Plantillas

Fecha: 2026-08-31
Alcance: master prompt §33-34 (LoyaltyCardTemplate / LoyaltyCardTemplateVersion), fase LOY-17.

## Dos niveles de aprobación, no uno

`LoyaltyCardsPermissions` (LOY-1) ya distinguía `TEMPLATE_APPROVE` de
`TEMPLATE_ACTIVATE` como acciones separadas — señal de que la plantilla
tiene su propio ciclo de vida de negocio (¿esta familia de diseño está
autorizada para existir?) INDEPENDIENTE de qué snapshot de diseño concreto
está vigente ahora mismo. Se modeló así: `LoyaltyCardTemplate` tiene su
propio estado (DRAFT→PENDING_APPROVAL→APPROVED→ACTIVE→ARCHIVED, con
segregación de funciones aprobador≠creador) y `LoyaltyCardTemplateVersion`
tiene el suyo, más ligero (DRAFT→APPROVED→ACTIVE→ARCHIVED, misma
segregación). Una plantilla solo puede activarse si tiene al menos una
versión APPROVED — esa validación cruzada vive en el caso de uso
(`ActivateLoyaltyCardTemplateVersionUseCase`), no en la entidad
`LoyaltyCardTemplate` misma, que no puede consultar otras filas.

Activar una versión nueva archiva automáticamente la versión ACTIVE previa
de la misma plantilla, en la MISMA transacción — nunca hay dos versiones
ACTIVE simultáneas para una plantilla (verificado con test:
`test_activating_new_version_archives_previous_active`).

## Bug real encontrado por un test que falló con el código de error equivocado

El primer borrador de `LoyaltyCardResult`/`_ERROR_CODES` (escrito en LOY-16,
antes de que existieran las excepciones de plantilla) nunca se extendió al
agregar las excepciones nuevas de LOY-17
(`InvalidLoyaltyCardTemplateVersionStateError` y compañía) — habrían caído
todas en el genérico `"VALIDATION"` en vez de un código específico como
`TEMPLATE_VERSION_INVALID_STATE`. Detectado por
`test_cannot_activate_unapproved_version` al escribir la aserción del
código esperado, antes de correr el test — mismo tipo de brecha "olvidé
registrar la excepción nueva en el mapeo de resultados" que otras fases ya
habían evitado por revisión, no por accidente. Corregido extendiendo
`backend/application/loyalty_cards/result.py` con las 6 excepciones nuevas
de plantilla/versión antes de correr la suite.

## Qué se construyó

Entidades `LoyaltyCardTemplate` y `LoyaltyCardTemplateVersion`
(`design_schema_json`: un esquema JSON DECLARATIVO — nunca código
ejecutable; la entidad solo garantiza que el campo no esté vacío, la
sanitización real es competencia del Diseñador en LOY-18).

Esquema `loyalty_card_templates`/`loyalty_card_template_versions` (extiende
`create_loyalty_cards_schema()`, migración 237, siguiendo el mismo patrón
"extender la función de esquema y re-invocarla" ya usado en Fidelidad
227-231), repositorios, `LoyaltyCardsUnitOfWork` extendido con
`templates`/`template_versions`, y `backend/application/loyalty_cards/
use_cases/template_use_cases.py`: creación/aprobación/archivado de
plantilla, creación de versión (numeración secuencial por plantilla),
aprobación y activación de versión (con el archivado automático descrito
arriba).

## Alcance honesto

- `design_schema_json` es un string opaco en esta fase — ningún parser,
  validador de layout, ni el Diseñador visual (Loyalty Card Studio) existen
  todavía; eso es LOY-18.
- Ningún caso de uso de `LoyaltyCard` (LOY-16) consume todavía
  `LoyaltyCardTemplate.active_version_id` al emitir una tarjeta física —
  la conexión entre "qué plantilla imprimir" y "qué tarjeta se emitió" es
  trabajo de LOY-21/22 (lotes/impresión).

## Tests

20 tests nuevos (`test_loyalty_card_template_domain.py`: 10;
`test_loyalty_card_template_use_cases.py`: 10), todos pasando. Verificado
con bootstrap real — migración 237 corre limpia, las 5 tablas
`loyalty_card*` existen juntas.

406 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos
juntos, sin regresión.

## Pendiente para fases futuras

- LOY-18 (Diseñador): Loyalty Card Studio, validación real de que
  `design_schema_json` es declarativo y seguro.
- LOY-19 (Importación): SVG/PDF/PNG → `design_schema_json`.
- LOY-21 (Lotes): consumir `LoyaltyCardTemplate.active_version_id` real.
