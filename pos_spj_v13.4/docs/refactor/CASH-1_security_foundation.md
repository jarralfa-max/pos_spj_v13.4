# CASH-1 — Seguridad base de Caja

Fecha: 2026-08-03  
Estado: `IMPLEMENTED` para contratos y políticas puras; integración operativa pendiente de CASH-2/CASH-4.

## Alcance entregado

- Catálogo cerrado de permisos `CASH_*`, separado por consulta, cajas, terminales, turnos, movimientos, conteos, cortes, diferencias, entregas, reembolsos, cajón, hardware, impresión, configuración y notificaciones.
- `CashAuthorizationPolicy` fail-closed: sin `PermissionChecker` configurado deniega; toda operación con sucursal exige `BranchScopeChecker`.
- `CashMonetaryLimitPolicy` configurable con umbral de autorización y hard cap, exclusivamente con `Decimal`.
- `CashSegregationOfDutiesPolicy` para conteo/diferencia, Corte Z/resolución, entrega/recepción, reembolso y reverso.
- Autorización en caliente por un segundo usuario, con permiso y scope revalidados en backend.
- `CashAuthorizationGrant` y `CashSecurityAuditEntry` inmutables, con UUIDv7 independiente y timestamp UTC.
- Auditoría obligatoria de autorizaciones: actor, entidad, sucursal, operación, motivo, monto, dispositivo y vínculo al grant.

## Decisiones de integración

- El catálogo legacy `CAJA.ver/abrir/cerrar/retiro/corte_z` permanece temporalmente solo para la navegación antigua. No se usa dentro del bounded context nuevo y se retirará al migrar la vista.
- Estas políticas no se conectan aún a `CashRegisterApplicationService`, porque dicho servicio delega a `FinanceService` sin UnitOfWork canónico. Integrarlo ahora permitiría auditoría fuera de la transacción.
- Los límites no tienen defaults de negocio. Deben ser cargados desde configuración por sucursal/usuario/operación en CASH-5.
- Los registros se persistirán junto con la operación y el outbox en CASH-3/CASH-4. En esta fase el contrato es un `AuditSink` inyectado.

## Tests

```text
tests/unit/cash_register/test_cash_register_security.py
tests/architecture/test_cash_register_security_foundation.py
```

Cobertura:

- Catálogo granular y ausencia de permisos generales.
- Autorización fail-closed.
- Scope por sucursal.
- Límites Decimal y rechazo de float.
- Segregación de funciones.
- Autorizador independiente.
- Grant y auditoría producidos en conjunto.
- Guardrail AST contra contratos float y permisos legacy en el contexto nuevo.

## Riesgos pendientes

- La UI y los Use Cases legacy todavía no consumen estas políticas.
- Falta persistencia transaccional de grants/auditoría.
- Falta resolver permisos y sucursales desde adaptadores reales del sistema.
- Falta configuración versionada de límites y vigencias.
- Falta redactar/migrar los permisos visibles en la matriz administrativa.

Siguiente fase: CASH-2, dominio de cajas, cajones, terminales, turnos, ledger, conteos, cortes, diferencias, entregas, policies y eventos. Los Use Cases deberán recibir explícitamente las políticas de CASH-1.
