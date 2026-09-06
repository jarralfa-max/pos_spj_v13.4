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

---

## Anexo — el segundo guardrail de §39, y por qué no es un cero

`tests/architecture/test_no_monetary_float.py` cubre el **código**; el anterior cubría el
**esquema**. Con esto quedan implementados los dos que §39 pedía.

### La medición

`float(<identificador monetario>)` en código productivo: **308 ocurrencias**.

| Área | Ocurrencias |
| --- | ---: |
| `core/` | 201 |
| `backend/` | 37 |
| `repositories/` | 31 |
| `modulos/` | 9 |
| `application/` | 8 |
| resto | 22 |
| **`backend/domain/`** | **0** |

Los focos son `core/services/sales_service.py` (34) y
`core/services/enterprise/finance_service.py` (20) — el SalesService legacy que §11 manda
eliminar.

### Por qué dos garantías y no un assert a cero

Un assert a cero con 308 violaciones sería un test rojo permanente: nadie lo lee y deja de
comunicar. Eso es precisamente el falso gate que §40 describe. En su lugar:

1. **`backend/domain/` se fija en CERO duro.** Ya está limpio hoy, y es la capa que §4
   obliga a mantener pura. Una regla que ya se cumple puede exigirse sin tolerancias.
2. **El resto queda bajo ratchet por área**: la deuda existente queda medida y **no puede
   crecer**. Una tercera prueba obliga a bajar la base cuando un contexto migra, para que
   el progreso quede registrado — es lo que evita que estas cifras se conviertan en las
   allowlists obsoletas que `05_IDENTITY_GUARDRAILS.md` documenta.

El gate de dominio se verificó introduciendo una violación real
(`float(row["precio_unitario"])` en un archivo temporal bajo `backend/domain/`): **falla**,
y vuelve a pasar al retirarla. No es un guard que sólo sabe pasar.

### `migrations/`: 379 columnas REAL, medidas y congeladas

El detector de esquema aplicado a `migrations/` encuentra **379** columnas REAL de dinero o
de magnitudes que se multiplican por dinero (292 son importes en sentido estricto; el resto
cantidades y pesos, que contaminan igual en cuanto se multiplican). La mayoría está en
`m000_base_schema.py`, e incluye literalmente las que §9 del prompt maestro enumera:
`credit_limit`, `credit_balance`, `precio`, `precio_compra`, `precio_minimo_venta`,
`limite_credito`, `saldo_pendiente`.

**No se convierten aquí, y la razón es de semántica, no de tamaño.** Pasar esas columnas a
TEXT cambia el resultado de cada `SUM(precio)`, `AVG(total)` y comparación numérica que el
SQL legacy hace sobre ellas — en silencio y sin que ninguna prueba lo detecte. A diferencia
del cambio de PK, que sólo endurecía una restricción, esto altera el **valor** devuelto. Es
un corte con su propia migración, su propio inventario de consultas afectadas y su propia
validación.

Mientras tanto queda medido y congelado en 379: puede bajar, nunca subir.

### Evidencia

```text
python -m pytest tests/architecture -q -p no:cacheprovider --tb=no
```

| Momento | Resultado |
| --- | --- |
| Tras `3a5698b0` | 28 failed, 746 passed, 1 skipped |
| Ahora | **28 failed, 752 passed**, 1 skipped |

Diferencia de conjuntos: **0 nuevos**. Los +6 son los guardrules añadidos.

### Lo que sigue abierto

La deuda de dinero en float **no se ha reducido**: se ha medido y acotado. 308 conversiones
en código y 379 columnas en migraciones siguen ahí. El siguiente paso real es el corte de
`core/services/sales_service.py` (§11), que concentra el mayor foco y que el prompt maestro
ya marca para eliminación.
