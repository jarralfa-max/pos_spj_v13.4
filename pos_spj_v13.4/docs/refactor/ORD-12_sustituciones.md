# ORD-12 — Sustituciones

Fecha: 2026-08-31. Alcance: master prompt §28-29 (propuesta, precio, aprobación, rechazo).

## Qué se construyó

- `SubstitutionType` enum (SAME_PRODUCT_DIFFERENT_PRESENTATION/EQUIVALENT_PRODUCT/
  CUSTOMER_APPROVED_ALTERNATIVE/NO_SUBSTITUTION) + `SubstitutionPolicy` (valida
  `substitution_allowed` y que la línea no esté en un estado terminal).
- Campos nuevos en `CustomerOrderLine`: `substitution_type`, `substitute_product_id`,
  `substitution_reason`, `pre_substitution_unit_price` (precio original conservado para
  auditoría), `proposed_substitution_unit_price` (precio del sustituto, aplicado solo al
  aceptar). Métodos: `propose_substitution()`, `accept_substitution()` (idempotente),
  `reject_substitution()` (idempotente).
- `CustomerOrder.propose_substitution()`/`accept_substitution()`/`reject_substitution()` —
  orquestación a nivel pedido.
- Casos de uso: `ProposeSubstitutionUseCase`, `AcceptSubstitutionUseCase`,
  `RejectSubstitutionUseCase` — reutilizan `SUBSTITUTION_PROPOSE`/
  `CUSTOMER_APPROVAL_OVERRIDE` de ORD-1, sin permisos nuevos.

## Decisiones

- **Reutiliza la MISMA maquinaria de aprobación del cliente que ORD-10/ORD-11**
  (`CustomerApprovalStatus`, `OrderLineStatus.PENDING_CUSTOMER_APPROVAL`, idempotencia,
  expiración vía `expire_customer_approval()` — una sustitución pendiente también expira
  con el mismo mecanismo, sin código adicional). Una línea solo puede tener UNA cosa
  pendiente de aprobación del cliente a la vez en este dominio (ajuste de peso O
  sustitución, nunca ambas simultáneamente) — simplificación deliberada, documentada, no
  un descuido.
- **`product_id` de la línea nunca cambia** — representa lo que el cliente pidió
  originalmente; `substitute_product_id` es un campo separado. Igual principio que
  `requested_quantity` nunca cambiando y `final_quantity` siendo el campo separado que sí
  se actualiza (ORD-2/ORD-10).
- **El precio original se conserva** (`pre_substitution_unit_price`) aunque `
  unit_price_snapshot` se sobrescriba al aceptar — necesario para mostrar "antes/después"
  en el ticket/notificación (§29), no solo para el cálculo del total.

## Tests

12 tests nuevos (7 dominio + 5 integración). Suite acumulada ORD-1..12: **174/174
pasando** (125 unitarios + 49 de integración, verificados por separado).

## Pendiente

- Recuperación automática tras rechazo (buscar otro sustituto, remover la línea,
  reembolso parcial) — una línea `REJECTED` por sustitución hoy es un estado terminal
  simple, igual que una `REJECTED` por ajuste de peso (ORD-10). No es parte del alcance de
  "proponer/aceptar/rechazar" que pide esta fase.
