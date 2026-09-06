# Fase 4d: dinero en Decimal — WhatsApp drafts y el guardrail global que faltaba

Fecha de validación: 2026-09-05. Rama: `claude/erp-financial-bounded-context-uqxz6b`.
Parte de: `82b09ba5`.

## Por qué no había nadie vigilando

Existían **cinco** guardrules de Decimal, todos por contexto:

    test_assets_use_decimal.py
    test_customers_crm_uses_decimal_for_credit.py
    test_inventory_uses_decimal.py
    test_pricing_uses_money_decimal.py
    test_transfers_use_decimal.py

Ninguno global. Un bounded context nuevo podía nacer con dinero en coma flotante
sin que ninguna prueba lo notara — y eso es exactamente lo que pasó.

## La violación encontrada

Barrido del esquema canónico: 30 apariciones de `REAL`, de las cuales la inmensa mayoría
son docstrings que **prohíben** su uso, y 8 son `latitude`/`longitude` (coordenadas
geográficas, donde la coma flotante es el tipo correcto).

Quedaban **4 violaciones reales**, todas en `whatsapp_schema.py`:

    whatsapp_order_draft_lines.quantity    REAL
    whatsapp_order_draft_lines.unit_price  REAL
    whatsapp_quote_draft_lines.quantity    REAL
    whatsapp_quote_draft_lines.unit_price  REAL

Y no era sólo el esquema: la pila entera usaba float.

    domain/whatsapp/entities/order_draft.py:44,46   quantity: float, unit_price: float
    domain/whatsapp/entities/order_draft.py:65      round(self.quantity * self.unit_price, 2)
    domain/whatsapp/entities/order_draft.py:135     round(sum(line.subtotal ...), 2)
    domain/whatsapp/entities/quote_draft.py:103     round(sum(line.subtotal ...), 2)

`round(float(...), 2)` sobre importes es literalmente el patrón que §9 prohíbe.

## Que el defecto era real, no teórico

| Operación | Con float | Con Decimal + HALF_UP |
| --- | ---: | ---: |
| `1 × 2.675` | **2.67** | **2.68** |
| `3 × 0.145` | **0.43** | **0.44** |

Un centavo **de menos** por línea, sistemático y silencioso. La causa es doble: 2.675 no
es representable en binario (se almacena como 2.674999999999999822…) y `round()` de Python
usa banker's rounding, no el redondeo comercial que un cliente espera ver cobrado.

Las pruebas nuevas fijan ambos casos y además dejan escrito el comportamiento anterior
(`assert round(1 * 2.675, 2) == 2.67`), de modo que el documento del defecto vive en el
código y no sólo aquí.

## Lo que se cambió

**Dominio** (`order_draft.py`, `quote_draft.py`): `quantity`/`unit_price` pasan a `Decimal`.
Se añaden dos helpers con su justificación:

- `to_decimal()` convierte **siempre pasando por `str`**. `Decimal(0.1)` arrastra el error
  binario; `Decimal(str(0.1))` da exactamente `0.1`. El borde acepta `Decimal | int | str |
  float` porque los flujos parsean texto de WhatsApp y el catálogo del ERP entrega floats
  (`ProductRef.price = float(...)`); rechazar float en la frontera habría roto a los
  llamadores sin mejorar la exactitud, normalizarlo con seguridad sí la mejora.
- `quantize_money()` usa `ROUND_HALF_UP` explícito. La aritmética intermedia se mantiene en
  Decimal completo; sólo el resultado presentado se cuantiza.

**Persistencia**: las cuatro columnas pasan a `TEXT`; los repositorios escriben
`str(Decimal)` y rehidratan con `Decimal(...)`.

**Compatibilidad aguas abajo**: `erp/bridge.py` normaliza con `float(it["cantidad"])` en su
frontera, así que recibir `Decimal` es seguro. Se verificó antes de cambiar, no después.
El bridge sigue usando float internamente para dinero — deuda **abierta**, de otro alcance.

## Guardrail global nuevo

`tests/architecture/test_no_monetary_real_schema.py`, que §39 exigía y no existía. Detecta
`REAL`/`FLOAT`/`DOUBLE PRECISION` en columnas cuyo nombre denota dinero o magnitud
multiplicada por dinero, sobre todo el esquema canónico. `latitude`/`longitude` quedan
exentas explícitamente, con una prueba que impide ampliar esa exención a importes por
descuido, y otra que impide que ajustar la lista de tokens convierta el guard en un no-op.

Verificado contra la versión de `HEAD` **anterior** al arreglo: el guard detecta ahí las
4 violaciones. No es un guard que sólo sabe pasar.

## Pruebas y evidencia

`whatsapp_service/` (con `PYTHONPATH` incluyendo el paquete `pos_spj_v13.4/`, separador
`;` en Windows):

```text
python -m pytest tests/ -q -p no:cacheprovider --continue-on-collection-errors
```

| Momento | Resultado |
| --- | --- |
| Antes | 680 passed, 1 failed, 6 errors |
| Después | **688 passed**, 1 failed, 6 errors |

Las 8 pruebas nuevas son las de Decimal. El fallo y los 6 errores son preexistentes y
ajenos: el fallo es un `PermissionError [WinError 32]` al liberar un archivo temporal en
Windows (verificado en aislamiento; el archivo no contiene ninguna referencia monetaria) y
los errores son de colección por rutas de importación.

`pos_spj_v13.4/`:

```text
python -m pytest tests/architecture -q -p no:cacheprovider --tb=no
```

| Momento | Resultado |
| --- | --- |
| Tras `82b09ba5` | 28 failed, 743 passed, 1 skipped |
| Ahora | **28 failed, 746 passed**, 1 skipped |

Diferencia de conjuntos: **0 nuevos**. Los +3 son el guardrail nuevo.

## Riesgos residuales

**`erp/bridge.py` sigue haciendo aritmética de dinero en float** (`sum(it["cantidad"] *
it["precio_unitario"])`, `total` calculado en float antes de escribir a `ventas`). Esta
fase no lo toca: es la ruta legacy de ventas, con su propio esquema `REAL`, y merece su
propio corte. El guardrail nuevo **no lo cubre**, porque sólo inspecciona el esquema
canónico bajo `backend/infrastructure/db/schema/` — `migrations/` conserva 653 apariciones
de `REAL` sin clasificar.

No existe todavía el `test_no_monetary_float.py` que §39 también pide (float en código, no
en esquema). Sin él, la deuda de `float()` sobre importes en código productivo sigue sin
medirse.

Las columnas cambian de tipo para instalaciones **nuevas**. SQLite es dinámicamente tipado
y los repositorios ahora escriben texto en ambos casos, así que una instalación existente
sigue funcionando; pero sus filas antiguas conservan valores REAL y al rehidratarlas
`Decimal(r[4])` recibirá un float almacenado. Los drafts son efímeros por diseño (§34: "el
draft conversacional no es el pedido canónico"), así que el riesgo real es bajo, pero no
es cero y no se ha probado sobre una base con datos previos.

## Siguiente fase

`test_no_monetary_float.py` para medir el `float()` sobre dinero en código productivo, y
clasificar las 653 apariciones de `REAL` en `migrations/` separando dinero de magnitudes
legítimas. Después, el corte del `erp/bridge.py`.
