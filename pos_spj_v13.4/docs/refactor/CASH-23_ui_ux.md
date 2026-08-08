# CASH-23 - UI/UX

## Alcance implementado

- Navegacion interna de Caja con rutas por operacion, cortes, control y administracion.
- Workspace PyQt responsive con `SideNav`, `QStackedWidget`, `PageHeader`, `KPIBar` y estados canonicos.
- Dialogos estandar para motivo, autorizacion en caliente y vista previa de impresion.
- Tema JUANIS aplicado al `SideNav` global desde `qss_builder.py`.
- Tooltips y metadatos accesibles en rutas, estados y campos de dialogo.
- Tests de arquitectura para evitar SQL, estilos inline, botones/dialogos fuera del sistema visual y regresiones de navegacion.

## Validacion manual

- [ ] Abrir modulo Caja desde la navegacion principal.
- [ ] Cambiar entre Resumen, Turnos, Ledger, Conteo ciego, Corte X, Corte Z, Diferencias, Entregas, Reembolsos, Hardware y Configuracion.
- [ ] Reducir la ventana y confirmar que la navegacion se mantiene usable.
- [ ] Probar tema claro y oscuro.
- [ ] Confirmar que los estados vacios explican que QueryService falta sin ocultar errores funcionales.
- [ ] Abrir dialogos de motivo, autorizacion e impresion desde los presenters que los conecten.
- [ ] Recorrer con teclado y lector de accesibilidad: nombres de modulo, navegacion y paginas deben estar disponibles.
