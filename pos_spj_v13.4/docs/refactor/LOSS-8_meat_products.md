# LOSS-8 — Productos cárnicos

Estado: implementado el 2026-08-03.

LOSS-8 amplía el análisis de producción de LOSS-7 sin crear catálogos paralelos.
La fuente única permanece en Productos:

- `species` para especies;
- `cut_classifications` para cortes y región anatómica;
- `cutting_scheme_versions` para el despiece inmutable y activo;
- `cutting_outputs` para producto, corte, rol y forma de medición.

Cada salida real transporta UUIDv7 de producto, especie, corte y lote opcional.
Piezas (`quantity`) y peso se conservan separadamente como `Decimal`. El
`measure_kind` determina si la salida configurada es `BY_PIECE` o `BY_WEIGHT`.

Los roles aceptados son `MAIN_PRODUCT`, `CO_PRODUCT`, `BY_PRODUCT`, `WASTE` y
`LOSS`. Coproductos y subproductos productivos participan en el rendimiento;
`WASTE` y `LOSS` se observan pero no inflan la salida productiva.

La integración falla cerrado cuando:

- la especie del producto de entrada no coincide con el despiece;
- el corte pertenece a otra especie;
- un producto no está configurado como salida;
- el rol coproducto/subproducto es diferente al configurado;
- piezas/peso contradicen el `measure_kind` del esquema.

`loss_meat_output_observations` conserva el detalle observado y referencia la
variación de rendimiento. Su esquema vive exclusivamente en la migración 174.
La persistencia continúa siendo atómica e idempotente con el análisis LOSS-7.

Verificación principal: despiece de 100 kg con producto principal de 60 kg/6
piezas, coproducto de 10 kg y subproducto de 14 kg. Rendimiento real 84 %;
genera 10 kg de merma normal y 6 kg anormal, con tres observaciones cárnicas.
