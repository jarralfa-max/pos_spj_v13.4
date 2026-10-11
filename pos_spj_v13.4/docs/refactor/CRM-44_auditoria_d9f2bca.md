# CRM-44 — Respuesta a la auditoría externa de Clientes/CRM (commit d9f2bca)

Fecha: 2026-10-09. Fuente: «Auditoría técnica de Clientes / CRM» sobre `d9f2bcaf`
(23 hallazgos, 18 reproducciones). Cada hallazgo se comprobó contra el código actual
(que ya incluía cambios posteriores a `d9f2bca`), se corrigió y se fijó con una prueba
que reproduce el escenario de la auditoría. Pruebas nuevas:

* `tests/integration/crm43/test_audit_d9f2bca_credit.py` — F01, F02, F23 (6)
* `tests/integration/crm43/test_audit_d9f2bca_integrity.py` — F03, F04, F05, F14, F15 (12)
* `tests/unit/test_audit_f13_customer_field.py` — F13 (3)
* `tests/integration/crm43/test_audit_d9f2bca_coherence.py` — F06–F12, F16 (16)

Verificado además sobre una copia de la base real (`audit_real.py`), con usuarios
cajero y gerente.

## Estado por hallazgo

| # | Sev. | Estado | Qué se hizo |
|---|------|--------|-------------|
| F01 | P0 | Corregido | `FinanceUnitOfWork(owns_transaction=False)` (mismo contrato que Inventario/Ventas); la cuenta por cobrar del cobro a crédito se escribe dentro de la transacción de la venta: si la venta falla, no queda deuda; reintento sin duplicar. |
| F02 | P0 | Corregido | `CustomerIdentityResolver` (canónico + histórico + fusionados); la exposición busca la deuda histórica por todas las identidades. Base real: crédito de $1,000 con $900 históricos → «disponible $100». |
| F03 | P1 | Corregido | `CRMRecordScopeGuard` cubre también clientes (`customer_id`); actividades/tareas/notas: lo de otra persona exige `…reasignar`, lo de un registro exige que el registro esté en el alcance (`WorkItemVisibility`); la importación que actualiza por id exige `CLIENTES.editar`. |
| F04 | P1 | Corregido | La búsqueda aplica la misma política de visibilidad que el expediente (cajero: parcial `•••2211`; gerente con datos sensibles: completo). Se sigue buscando por teléfono. Pedidos no propone un teléfono enmascarado. |
| F05 | P1 | Corregido | Alta, alta rápida del POS e importación guardan teléfono/correo como contacto principal y el RFC como perfil fiscal, en la misma transacción; un dato inválido rechaza la fila sin crear nada a medias. |
| F06 | P1 | Corregido | Fusión: un solo contacto principal y un domicilio predeterminado por tipo; el crédito del fusionado pasa al superviviente (o se cierra si ambos tenían); su deuda cuenta para el superviviente; el perfil fiscal del fusionado ya no se borra. |
| F07 | P1 | Corregido | Concurrencia optimista en el maestro (`WHERE id=? AND version=?`); el segundo escritor recibe `CONFLICT` y no pisa el primer cambio. |
| F08 | P1 | Corregido | Avanzar de etapa cuenta las actividades COMPLETADAS de la oportunidad (canceladas o de otro registro no cuentan). |
| F09 | P1 | Corregido | Alta de oportunidad: cliente existente y vigente, etapa existente/activa/no de cierre; `probability=None` toma la de la etapa y un 0 explícito se respeta; valor negativo o no finito rechazado en alta y edición. |
| F10 | P1 | Ya corregido hoy | Cada regla y registro con su propia llave de idempotencia (cierre de pendientes de CRM-43); prueba nueva: dos reglas → dos tareas. |
| F11 | P1 | Corregido | La pausa guarda su inicio y al reanudar recorre los vencimientos; varias pausas se suman (`paused_seconds`); resultado del SLA separado (`MET`/`MISSED`, «Cumplido»/«Incumplido»); «Resuelto» ya no es «Cumplido». Migración 322. Calendario hábil: pendiente (no hay calendarios modelados). |
| F12 | P1 | Corregido | El historial busca ventas por todas las identidades (la vista unificada expone el id canónico en sus filas canónicas). |
| F13 | P1 | Corregido | Escribir o borrar en el buscador invalida la selección; guardar un campo obligatorio exige volver a elegir. `SearchSelector.text_edited`. |
| F14 | P1 | Corregido | `CustomerContactPerson.update()` aplica las mismas reglas que el alta (nombre obligatorio, E.164, correo válido) y normaliza. |
| F15 | P1 | Corregido | La anonimización trata contactos (nombre genérico, sin teléfono/correo, inactivos) y domicilios no fiscales; conserva RFC, razón social y domicilio fiscal/facturación por obligación fiscal. Pendiente: datos en otros contextos (notas CRM, WhatsApp). |
| F16 | P2 | Corregido | Conversión en un paso (sólo cliente, o cliente + oportunidad; misma transacción, `CRMUnitOfWork(owns_transaction=False)`); el prospecto guarda `converted_customer_id`/`converted_opportunity_id` (migración 321); reintento sin otro cliente; oportunidad para otro cliente rechazada. |
| F17 | P2 | Corregido (CRM-43 hoy) | Siete disparadores por tiempo, aviso y prioridad, ciclo de fondo, entrega de recordatorios; los fallos de evaluación ahora se registran como advertencia (antes en debug). Pendiente: despachador general de los outbox de cada contexto. |
| F18 | P2 | Parcial | Contrato `owns_transaction` en Finanzas y CRM; resolvedor de identidad único. La introducción de puertos en todos los casos de uso es trabajo incremental aparte. |
| F19 | P2 | Parcial | Consolidados: identidad (`CustomerIdentityResolver`), alta con contacto/fiscal (`attach_contact_and_tax`), validación de contactos en el dominio. Los ocho `_emit` idénticos siguen (repetición literal, sin divergencia de negocio). |
| F20 | P2 | Corregido | Producto de interés desde el catálogo (queda su id) con cantidad decimal; texto libre sólo para lo no catalogado. |
| F21 | P2 | Parcial | Tablero: prospectos pendientes contados en SQL; pronóstico sobre todas las oportunidades abiertas (sin tope de 5,000). Las bandejas siguen cargando y filtrando en memoria (paginación en backend: pendiente). |
| F22 | P2 | Parcial | El tablero usa la sucursal activa y cuenta los casos vencidos dentro del alcance (antes, los de toda la empresa). TERRITORY/PORTFOLIO siguen sin membresía modelada (fallan cerrados, como ya documentaba el código). |
| F23 | P2 | Corregido | El cobro a crédito fija el vencimiento pactado del documento con el plazo vigente; la exposición lo usa y los documentos viejos conservan el suyo; «documentos vigentes»/«sucursal permitida» ya no se dan por verificados (`None` = sin regla). |

Las 3 pruebas que la auditoría reportó fallando (`test_customers_crm_directory_pages.py`)
ya se habían reescrito con enumerados reales en CRM-43 y pasan.

## Migraciones

| # | Qué hace |
|---|----------|
| 321 | `leads.converted_customer_id`/`converted_opportunity_id`; completa el cliente de los ya convertidos desde el outbox. |
| 322 | `sla_instances`: `paused_at`, `paused_seconds`, `first_response_outcome`, `resolution_outcome`; calcula el resultado de las ya resueltas. |

## Pendiente (decisión o trabajo aparte)

* Calendario hábil y días festivos para SLA (F11).
* Anonimización de datos personales fuera del maestro: notas CRM, conversaciones de WhatsApp (F15).
* Paginación y filtros en backend para las bandejas (F21); membresías de territorio y cartera (F22).
* Puertos de unidad de trabajo/repositorio en los casos de uso (F18).
