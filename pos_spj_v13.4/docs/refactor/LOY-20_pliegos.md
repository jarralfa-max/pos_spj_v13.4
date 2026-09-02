# LOY-20 — Pliegos 12×18

Fecha: 2026-08-31
Alcance: master prompt §38-40 (LoyaltyCardSheetProfile, LoyaltyCardImpositionProfile, sangrado/bleed, área
de seguridad/safe area, calles/gutter), fase LOY-20.

## "12x18" nunca es un literal de milímetros

El nombre de la fase ("Pliegos 12×18") se refiere a un tamaño de pliego en PULGADAS, la unidad estándar de
la industria de impresión de gran formato. En vez de escribir `304.8`/`457.2` como literales mágicos en
algún lado, `LoyaltyCardSheetProfile.standard_12x18()` deriva esos milímetros de la conversión real
(`Decimal("12") * MM_PER_INCH`, con `MM_PER_INCH = Decimal("25.4")` como constante nombrada) — el factor de
conversión queda visible y auditable en el código, no escondido dentro de un número ya calculado. Cualquier
otro tamaño de pliego (carta, A3, lo que sea) se crea con `LoyaltyCardSheetProfile.create()` pasando
milímetros directamente; `standard_12x18()` es solo el atajo con nombre para la referencia de esta fase.

## Columnas/filas son derivadas, nunca aceptadas como input

`LoyaltyCardImpositionProfile.create()` no acepta `columns`/`rows` como parámetros del llamador — los
calcula `ImpositionPolicy.compute()` (una función pura de geometría, sin entidades ni IO) a partir del área
imprimible real del pliego y el tamaño de tarjeta + sangrado + calle. Esto es deliberado: un llamador no
puede mentir sobre cuántas tarjetas caben en un pliego. La fórmula: cada tarjeta ocupa
`(ancho_tarjeta + 2×sangrado)` más una calle hacia su vecina, así que
`columnas = floor((imprimible + calle) / (celda + calle))` — la misma lógica se aplica a filas. Si el
resultado da columnas o filas en cero, se levanta `CardDoesNotFitOnSheetError` en vez de un perfil con cero
tarjetas por pliego.

## Validación de área de seguridad

`safe_area_mm` (margen interno dentro del cual todo contenido crítico debe permanecer, por tolerancia de
corte) se valida contra la dimensión MÁS PEQUEÑA de la tarjeta: si `safe_area_mm * 2 >= min(ancho, alto)`,
no quedaría área de contenido utilizable, y se rechaza — un valor de área de seguridad técnicamente "válido"
en aislamiento (positivo) pero que consume toda la tarjeta es igual de inválido en la práctica.

## Qué se construyó

`LoyaltyCardSheetProfile` (dimensiones + márgenes de pliego, `printable_width_mm()`/`printable_height_mm()`,
activar/desactivar) y `LoyaltyCardImpositionProfile` (tamaño de tarjeta + sangrado + área de seguridad +
calles, columnas/filas/tarjetas-por-pliego derivadas). Política pura `ImpositionPolicy.compute()`.

Esquema `loyalty_card_sheet_profiles`/`loyalty_card_imposition_profiles` (extiende
`create_loyalty_cards_schema()`, migración 238, mismo patrón de extensión que 237), repositorios,
`LoyaltyCardsUnitOfWork` extendido, y `backend/application/loyalty_cards/use_cases/sheet_use_cases.py`:
creación de pliego (genérico y el atajo `standard_12x18`), creación de perfil de imposición (valida que el
pliego exista antes de calcular la geometría).

## Alcance honesto

- Ningún caso de uso conecta todavía un `LoyaltyCardImpositionProfile` con un `LoyaltyCardTemplate` real — es
  decir, la fase calcula "cuántas tarjetas de ESTE tamaño caben en ESTE pliego" mas no "cuántas tarjetas con
  ESTA plantilla activa caben" — esa integración es de LOY-21 (Lotes), que sí conoce ambos conceptos.
- Sin generación de PDF de imposición real (el layout físico para enviar a imprenta) — eso también es
  competencia de LOY-21/22.

## Tests

18 tests nuevos (`test_sheet_imposition_domain.py`: 13; `test_sheet_use_cases.py`: 5), todos pasando en el
primer intento real. Verificado con bootstrap real — migración 238 corre limpia, las 7 tablas
`loyalty_card*` existen juntas.

464 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-21 (Lotes): `LoyaltyCardBatch`/`LoyaltyCardBatchItem`, consumiendo un `LoyaltyCardTemplate` activo +
  un `LoyaltyCardImpositionProfile` real para calcular cuántos pliegos necesita un lote de N tarjetas.
- LOY-22 (Impresión): generación real del PDF de imposición.
