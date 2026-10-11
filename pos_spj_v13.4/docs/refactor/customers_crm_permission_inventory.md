# Clientes y CRM — inventario de permisos (CRM-43, 2026-10-09)

Fuente de verdad: `backend/application/customers/permissions.py` (CLIENTES.*) y
`backend/application/crm/permissions.py` (CRM.*), registrados en el catálogo de
permisos (`backend/application/security/permission_catalog.py`). La siembra por rol es la
migración 314 (decisión del usuario «matriz completa», 2026-10-08). La autorización
siempre es por código efectivo (`session.tiene_permiso`), nunca por nombre de rol (§59);
dueño y administrador además tienen paso libre por rol en el evaluador de sesión.

Puerta del menú: `CLIENTES_CRM.ver` (los cinco roles con acceso). Almacén y repartidor:
ningún código.

Alcance de datos (§60): clientes globales (`CLIENTES.ver.compania` para todos);
prospectos/oportunidades/casos — gerente `*.ver.sucursal`, cajero `casos.ver.propia`,
solo lectura `*.ver.sucursal`. Ejes nuevos de CRM-43: `CRM.leads|oportunidades|casos.ver.sucursal`
y `.ver.compania`.

Códigos nuevos en CRM-43: `CRM.pipeline.configurar`, los seis ejes de alcance anteriores.

Segregación de funciones (§73) — la aplica el caso de uso, no el rol: quien solicita
crédito no lo aprueba; la fusión la ejecuta alguien distinto de quien la propuso; la
importación sensible la aprueba otra persona; la anonimización exige un autorizador
distinto de quien registró la solicitud; ninguna operación borra bitácora.

Totales por rol: dueño 182, admin 182, gerente 155, cajero 46, solo lectura 35.

| Código | system_owner | admin | gerente | cajero | solo_lectura |
|---|---|---|---|---|---|
| `CLIENTES.acceso` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.dashboard.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.buscar` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.buscar.global` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.configuracion.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.configuracion.editar` | ✔ | ✔ |  |  |  |
| `CLIENTES.auditoria.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.ver.propia` | ✔ | ✔ |  |  |  |
| `CLIENTES.ver.equipo` | ✔ | ✔ |  |  |  |
| `CLIENTES.ver.sucursal` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.ver.territorio` | ✔ | ✔ |  |  |  |
| `CLIENTES.ver.cartera` | ✔ | ✔ |  |  |  |
| `CLIENTES.ver.compania` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.editar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.editar.propia` | ✔ | ✔ |  |  |  |
| `CLIENTES.editar.sensible` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.activar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.desactivar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.suspender` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.bloquear` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.cerrar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.reabrir` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.anonimizar` | ✔ | ✔ |  |  |  |
| `CLIENTES.contacto.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.contacto.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.contacto.editar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.contacto.eliminar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.contacto.verificar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.contacto.marcar_principal` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.direccion.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.direccion.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.direccion.editar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.direccion.eliminar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.direccion.marcar_predeterminada` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.fiscal.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.fiscal.editar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.fiscal.validar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.ver_resumen` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.credito.ver_sensible` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.solicitar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.revisar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.aprobar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.rechazar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.limite.editar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.limite.sobrescribir` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.suspender` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.bloquear` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.cerrar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.reabrir` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.historial.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.credito.exportar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.consentimiento.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.consentimiento.capturar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.consentimiento.retirar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.consentimiento.evidencia.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.preferencia_comunicacion.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.preferencia_comunicacion.gestionar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.privacidad.solicitud.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.privacidad.solicitud.crear` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.privacidad.solicitud.procesar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.privacidad.solicitud.aprobar` | ✔ | ✔ |  |  |  |
| `CLIENTES.sensible.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.sensible.exportar` | ✔ | ✔ |  |  |  |
| `CLIENTES.sensible.desenmascarar` | ✔ | ✔ |  |  |  |
| `CLIENTES.calidad.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CLIENTES.calidad.resolver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.duplicados.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CLIENTES.duplicados.revisar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.duplicados.descartar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.duplicados.fusionar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.importar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.importar.aprobar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.exportar` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.actualizacion_masiva` | ✔ | ✔ |  |  |  |
| `CLIENTES.elegibilidad_comercial.verificar` | ✔ | ✔ | ✔ | ✔ |  |
| `CLIENTES.pedidos.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.entregas.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.fidelidad.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.whatsapp.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CLIENTES.sync_conflictos.ver` | ✔ | ✔ | ✔ |  |  |
| `CLIENTES.sync_conflictos.resolver` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.leads.ver.propia` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.ver.equipo` | ✔ | ✔ |  |  |  |
| `CRM.leads.ver.sucursal` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.leads.ver.compania` | ✔ | ✔ |  |  |  |
| `CRM.leads.crear` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.editar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.calificar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.descalificar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.convertir` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.archivar` | ✔ | ✔ | ✔ |  |  |
| `CRM.leads.exportar` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.oportunidades.ver.propia` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.ver.equipo` | ✔ | ✔ |  |  |  |
| `CRM.oportunidades.ver.sucursal` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.oportunidades.ver.compania` | ✔ | ✔ |  |  |  |
| `CRM.oportunidades.crear` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.editar` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.cambiar_etapa` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.sobrescribir_etapa` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.marcar_ganada` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.marcar_perdida` | ✔ | ✔ | ✔ |  |  |
| `CRM.oportunidades.reabrir` | ✔ | ✔ | ✔ |  |  |
| `CRM.pipeline.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.pipeline.configurar` | ✔ | ✔ |  |  |  |
| `CRM.forecast.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.forecast.ver.equipo` | ✔ | ✔ | ✔ |  |  |
| `CRM.forecast.ver.compania` | ✔ | ✔ |  |  |  |
| `CRM.actividades.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CRM.actividades.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.actividades.editar` | ✔ | ✔ | ✔ |  |  |
| `CRM.actividades.completar` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.actividades.cancelar` | ✔ | ✔ | ✔ |  |  |
| `CRM.actividades.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.tareas.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CRM.tareas.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.tareas.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.tareas.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.tareas.completar` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.tareas.cancelar` | ✔ | ✔ | ✔ |  |  |
| `CRM.tareas.reprogramar` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.notas.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CRM.notas.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.notas.editar.propia` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.notas.eliminar.propia` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.notas.ver.privada` | ✔ | ✔ | ✔ |  |  |
| `CRM.notas.crear.privada` | ✔ | ✔ | ✔ |  |  |
| `CRM.recordatorios.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.casos.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CRM.casos.ver.propia` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.casos.ver.equipo` | ✔ | ✔ |  |  |  |
| `CRM.casos.ver.sucursal` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.casos.ver.compania` | ✔ | ✔ |  |  |  |
| `CRM.casos.crear` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.casos.editar` | ✔ | ✔ | ✔ | ✔ |  |
| `CRM.casos.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.escalar` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.resolver` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.cerrar` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.reabrir` | ✔ | ✔ | ✔ |  |  |
| `CRM.casos.ver.sensible` | ✔ | ✔ | ✔ |  |  |
| `CRM.sla.ver` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CRM.sla.gestionar` | ✔ | ✔ |  |  |  |
| `CRM.sla.sobrescribir` | ✔ | ✔ | ✔ |  |  |
| `CRM.segmentos.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.segmentos.crear` | ✔ | ✔ | ✔ |  |  |
| `CRM.segmentos.editar` | ✔ | ✔ | ✔ |  |  |
| `CRM.segmentos.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.segmentos.remover` | ✔ | ✔ | ✔ |  |  |
| `CRM.etiquetas.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.etiquetas.crear` | ✔ | ✔ | ✔ |  |  |
| `CRM.etiquetas.editar` | ✔ | ✔ | ✔ |  |  |
| `CRM.etiquetas.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.etiquetas.remover` | ✔ | ✔ | ✔ |  |  |
| `CRM.territorios.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.territorios.gestionar` | ✔ | ✔ |  |  |  |
| `CRM.carteras.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.carteras.gestionar` | ✔ | ✔ |  |  |  |
| `CRM.carteras.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.propietario.ver` | ✔ | ✔ | ✔ |  | ✔ |
| `CRM.propietario.asignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.propietario.reasignar` | ✔ | ✔ | ✔ |  |  |
| `CRM.bi.exportar` | ✔ | ✔ |  |  |  |
| `CRM.automatizaciones.ver` | ✔ | ✔ | ✔ |  |  |
| `CRM.automatizaciones.crear` | ✔ | ✔ |  |  |  |
| `CRM.automatizaciones.editar` | ✔ | ✔ |  |  |  |
| `CRM.automatizaciones.activar` | ✔ | ✔ |  |  |  |
| `CRM.automatizaciones.desactivar` | ✔ | ✔ |  |  |  |
| `CRM.automatizaciones.ver_ejecuciones` | ✔ | ✔ | ✔ |  |  |
| `CRM.sync_conflictos.ver` | ✔ | ✔ | ✔ |  |  |
| `CRM.sync_conflictos.resolver` | ✔ | ✔ | ✔ |  |  |
