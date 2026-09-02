# LOY-18 — Diseñador (Loyalty Card Studio)

Fecha: 2026-08-31
Alcance: master prompt §34-36 ("no código ejecutable en las plantillas"), fase LOY-18.

## La regla de seguridad central: allowlist cerrada, nunca sanitización

`backend/domain/loyalty_cards/design_schema.py::validate_design_schema()` es la primera pieza de este
pipeline dedicada enteramente a validar contenido cuasi-visual, no datos de negocio. Se implementó como una
allowlist cerrada — tipos de elemento conocidos (`TEXT`/`IMAGE`/`QR`/`BARCODE`/`SHAPE`), campos conocidos por
tipo, y el contenido de `TEXT` solo puede referenciar un vocabulario fijo de placeholders `{{token}}`
(`customer_name`, `card_number`, `membership_tier`, `points_balance`, `expiry_date`, `program_name`).
Cualquier cosa fuera de eso se RECHAZA, nunca se sanitiza ni se repara — mismo principio que "SQL seguro"
(rechazar entrada insegura, no repararla) aplicado aquí a marcado de diseño.

`LoyaltyCardTemplateVersion.__post_init__` ahora llama a este validador en vez del simple chequeo "no vacío"
que LOY-17 dejó como placeholder honesto (su propio doc decía "eso es LOY-18") — una versión de plantilla no
puede construirse, guardarse, ni rehidratarse desde la base de datos con un diseño inválido.

## Bug real de seguridad encontrado por un test, corregido antes de reportar la fase como lista

El primer borrador de la regex de placeholders (`\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}`) exigía que TODO el
contenido entre `{{` y `}}` fuera un identificador válido para siquiera intentar hacer match. Un test
deliberadamente adversarial (`test_unknown_placeholder_rejected`, con contenido
`{{__import__('os')}}`) reveló que ese patrón de código malicioso NO calza con la regex en absoluto —
`finditer()` no encuentra ningún match, así que el validador nunca lo evalúa contra la allowlist y lo deja
pasar como texto ordinario sin marcar error. Es decir: la regex demasiado estricta para "reconocer" un
placeholder terminaba siendo demasiado permisiva para "bloquear" contenido peligroso con forma de
placeholder. Corregido ANTES de reportar la fase como terminada: la regex ahora captura cualquier span
`{{...}}` sin importar su contenido interno (`\{\{(.*?)\}\}`), y luego se valida ese contenido capturado
contra un patrón de identificador Y contra la allowlist por separado — así `{{__import__('os')}}` sí se
captura y sí se rechaza (su contenido interno no es un identificador simple ni está en la allowlist). Este es
el tipo de bug que una regex "razonable a primera vista" esconde: probar con una entrada adversarial
real, no solo con el caso feliz, fue lo que lo sacó a la luz.

## Ajuste retroactivo a los fixtures de LOY-17

Los tests de LOY-17 usaban JSON de relleno no estructurado (`"{}"`, `'{"layout":"classic"}'`) como
`design_schema_json` — válido bajo el chequeo laxo de esa fase, inválido bajo el validador real de LOY-18.
Se reemplazaron por un esquema mínimo válido y consistente (`_VALID_SCHEMA`, un canvas 85.6×54mm con un
elemento `TEXT`) en ambos archivos de test de LOY-17 — un ajuste mecánico y esperado de fixtures, no una
pérdida de cobertura: las 26 aserciones de esos tests siguen probando exactamente lo mismo que antes.

## Qué se construyó

`backend/domain/loyalty_cards/design_schema.py` (`validate_design_schema()`, sin estado, sin IO — una
función de dominio pura) y una nueva excepción `InvalidCardDesignSchemaError`, registrada en
`backend/application/loyalty_cards/result.py` (`INVALID_DESIGN_SCHEMA`). Ningún caso de uso nuevo — la
validación se activó en el punto de entrada existente (`LoyaltyCardTemplateVersion.__post_init__`), sin
necesidad de tocar `CreateLoyaltyCardTemplateVersionUseCase`.

## Alcance honesto

- Sin motor de renderizado (no se genera PDF/imagen desde el esquema todavía) — eso, junto con importación
  SVG/PDF/PNG, es LOY-19.
- Sin UI de arrastrar-y-soltar — este dominio define el CONTRATO que cualquier futura UI de diseño debe
  producir y respetar, no la UI misma.
- El vocabulario de placeholders/elementos es deliberadamente pequeño; ampliarlo (p. ej. `IMAGE.source` con
  una foto de producto, códigos QR con más de un `data_source`) es una extensión aditiva futura, no una
  limitación estructural.

## Tests

16 tests nuevos (`tests/unit/loyalty_cards/test_design_schema.py`), todos pasando tras la corrección de la
regex descrita arriba. 422 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos juntos
(incluyendo los 26 de LOY-16/17 con fixtures actualizados), sin regresión.

## Pendiente para fases futuras

- LOY-19 (Importación): SVG/PDF/PNG/formato nativo → `design_schema_json`, con la misma disciplina de
  validar-antes-de-aceptar en vez de sanitizar después.
- LOY-20 (Pliegos 12×18): usar `canvas.width_mm`/`height_mm` para calcular imposición real.
- LOY-21+ (Lotes/Impresión): consumir `design_schema_json` para renderizar tarjetas reales.
