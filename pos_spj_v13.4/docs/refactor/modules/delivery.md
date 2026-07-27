# Módulo DELIVERY — auditoría F7 / Fase A

## Estado: Fase A (identidad/defaults)

La UI de delivery no ejecuta SQL crudo, pero tenía 7 defaults arbitrarios de
sucursal `1` y 2 casts `int(branch)`. Todo eliminado en Fase A (UUID-ready).

## Baseline F0 + resultado

`tests/architecture/test_delivery_guardrails.py` (ratchet, solo baja).

| Patrón | F0 | Ahora |
|---|---|---|
| `int(getattr ... sucursal_id)` | 2 | **0** ✅ |
| default `branch/sucursal = 1` | 7 | **0** ✅ |
| SELECT / UPDATE (comentarios/prosa) | 1 / 2 | 1 / 2 |

## Hecho

- `_cargar_drivers`: `int(getattr(parent,"sucursal_id",1) or 1)` → `str(...)`.
- `_get_branch_id_for_counts() -> int` → `-> str`, retorno `str(...)`. Sus 3
  callers la usan como `branch_id=` (param SQL) — str correcto, sin aritmética.
- 5 `getattr/get(...,'sucursal_id',1)` (reserva, audit, evento, payload, fila) →
  default `""` (nunca sucursal 1; evita fuga entre sucursales). `activo` mantiene
  su default 1 (es flag, no identidad).

## Verificación
- Guardrail verde. Suite de delivery: 7 fallos pre-existentes idénticos pre/post
  (proyección/outbox, ajenos a este cambio) — **0 regresión nueva**.

## Pendiente
- **Fase B:** identidad de escritura del delivery service + esquema TEXT.
