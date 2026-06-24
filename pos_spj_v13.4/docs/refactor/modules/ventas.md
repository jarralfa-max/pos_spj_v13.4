# Módulo VENTAS — auditoría F7 / Fase A

## Estado: Fase A iniciada

VENTAS es el core operacional (4833 líneas). Identidad de escritura (`lastrowid`)
**no** está aquí — vive en el sales service y está acoplada al corte de esquema
(Fase B). Lo seguro en Fase A: quitar casts de identidad, defaults `branch=1` y
extraer SQL de la UI.

## Baseline F0 (medido 2026-06)

`tests/architecture/test_ventas_guardrails.py` (ratchet, solo baja).

| Patrón | F0 | Ahora |
|---|---|---|
| `int(_id)` / `int(getattr sucursal_id)` | 1 | **0** ✅ |
| default `branch/sucursal = 1` | 4 | **0** ✅ |
| `.execute` en UI | 6 | 6 (pendiente) |
| SELECT / UPDATE en UI | 8 / 9 | 8 / 9 (pendiente) |

## Hecho en esta Fase A

- `ModuloVentas.__init__`: `sucursal_id = 1` → desde `container` (sesión), sin literal.
- 3 fallbacks `getattr(self,'sucursal_id',1)` → `"" or ""` (sin sucursal 1).
- `int(getattr(self,"sucursal_id",1) or 1)` en reversión de venta → `str(...)`
  (sin cast de identidad ni default arbitrario).
- 2 `operation_id` con `uuid4()` → `new_uuid()` (fuente única UUIDv7). Los `uuid4`
  restantes son tokens QR / `_uid` de UI, no identidad de dominio.

## F5 SQL en UI — hecho

Las 6 lecturas SQL crudas de la UI (header de ticket, items con producto, items
básicos, búsqueda por folio, contenedor QR) extraídas a
`backend/infrastructure/db/repositories/sales_read_repository.py` (PyQt-free),
cubiertas por `tests/unit/test_sales_read_repository.py` (5 tests headless).
La UI (`_reimprimir_ultima_venta`, PDF de auditoría, diálogo cancelar venta,
scanner QR) ahora delega y consume dicts/tuplas.

`modulos/ventas.py`: `.execute` de UI 6→0 (el único `.execute` restante es
`create_customer_uc.execute()`, un use case). `venta_id` ya no se castea con `int`.
Los SELECT/UPDATE que el guardrail aún cuenta son comentarios/prosa, no SQL.

## Pendiente

- **Fase B:** identidad de escritura del sales service (`lastrowid`) + esquema TEXT.
