# TRF-4 — Sidebar y navegación de Transferencias

## Entrada y navegación canónica

The global application continues to expose a single **Transferencias** entry
during controlled migration. Its canonical internal sidebar is declarative at
`frontend/desktop/modules/transfers/navigation/transfers_sidebar.py` and has the
following Spanish navigation order: Resumen, Solicitudes, Aprobaciones, Picking,
Listas para despacho, En tránsito, Recepciones, Diferencias, Devoluciones,
Sugerencias, Trazabilidad, Alertas, Análisis, Auditoría, Configuración.

The sidebar itself has no Qt, SQL, repository, inventory write, local KPI, or
authorization logic. The application shell renders this data through the SPJ
`ModuleSidebar`; backend Use Cases remain the security boundary.

## Routes, permissions, and badges

`transfers_routes.py` recognizes only the internal canonical route IDs and
rejects unknown/legacy IDs. Each navigation entry declares its granular
`TRANSFERS_*` visibility permission. `TransferNavigationQueryService` obtains
the six permitted sidebar/KPI badge counts from an injected read port scoped by
the current user and branch:

* pending requests;
* pending approvals;
* ready to dispatch;
* in transit;
* pending receipts; and
* open differences.

Page factories are deliberately deferred until their workflow phases implement
the corresponding presentation pages; this phase establishes one non-legacy
navigation contract rather than adding a second functioning UI route.
