"""Canonical module permission catalog for SPJ POS.

This catalog is the source of truth for module visibility. UI navigation,
Configuración permission matrix and SessionContext checks must all use the same
`MODULO.accion` permission code format.
"""
from __future__ import annotations

CANONICAL_MODULE_PERMISSIONS: dict[str, list[str]] = {
    "DASHBOARD": ["ver"],
    # Bounded context de Ventas/POS (granular; ver
    # backend/application/sales/permissions.py). Los 4 códigos planos
    # originales (ver/crear/cancelar/descuento) se conservan por
    # compatibilidad con checks existentes — no autorizar código nuevo
    # contra ellos, usar SalesPermissions.
    "POS": [
        "ver", "crear", "cancelar", "descuento",
        "acceso", "abrir",
        "venta.linea_agregar", "venta.linea_actualizar", "venta.linea_eliminar",
        "venta.completar", "venta.suspender", "venta.reanudar",
        "descuento.personalizado", "descuento.sobrescribir", "precio.sobrescribir",
        "pago.efectivo", "pago.tarjeta", "pago.transferencia", "pago.mixto",
        "pago.credito", "pago.mercado_pago",
        "devolucion", "reverso", "ticket.reimprimir", "factura.solicitar",
        "cajon.abrir_manual", "bascula.usar", "dispositivo.diagnostico_ver",
    ],
    # Bounded context de Caja (granular; ver backend/application/cash_register/permissions.py).
    "CAJA": [
        "ver", "ver.sucursal_propia", "ver.sucursales_asignadas",
        "ver.todas_sucursales", "ver.importes_sensibles", "ver.auditoria",
        "exportar",
        "caja.ver", "caja.crear", "caja.editar", "caja.activar",
        "caja.bloquear", "caja.retirar",
        "cajon.ver", "cajon.gestionar", "cajon.abrir",
        "cajon.abrir_sin_venta",
        "terminal.ver", "terminal.gestionar", "terminal.operar",
        "turno.ver", "turno.abrir", "turno.suspender", "turno.reanudar",
        "turno.pre_cerrar", "turno.cerrar", "turno.forzar_cierre",
        "turno.reasignar",
        "movimiento.ver", "movimiento.ingreso", "movimiento.retiro",
        "movimiento.safe_drop", "movimiento.reversar",
        "movimiento.autorizar_exceso",
        "conteo.ver", "conteo.iniciar", "conteo.capturar",
        "conteo.confirmar", "conteo.ver_esperado", "conteo.cancelar",
        "conteo.sobrescribir",
        "corte_x.ver", "corte_x.generar", "corte_x.imprimir",
        "corte_x.reimprimir",
        "corte_z.ver", "corte_z.generar", "corte_z.revisar",
        "corte_z.imprimir", "corte_z.reimprimir",
        "diferencia.ver", "diferencia.explicar", "diferencia.revisar",
        "diferencia.resolver", "diferencia.castigar",
        "retiro_seguridad.ver", "retiro_seguridad.crear",
        "retiro_seguridad.autorizar",
        "entrega.ver", "entrega.preparar", "entrega.entregar",
        "entrega.recibir", "entrega.disputar", "entrega.cancelar",
        "deposito.ver", "deposito.preparar", "deposito.cancelar",
        "pago.ver", "pago.registrar", "pago.reversar",
        "medio_pago.ver", "medio_pago.gestionar",
        "terminal_pago.ver", "terminal_pago.gestionar",
        "terminal_pago.conciliar_operacion",
        "reembolso.ver", "reembolso.solicitar", "reembolso.ejecutar",
        "reembolso.autorizar", "reembolso.sobrescribir",
        "evento_cajon.ver",
        "hardware.ver", "hardware.diagnosticar", "hardware.gestionar",
        "imprimir", "reimprimir",
        "configuracion.ver", "configuracion.editar",
        "notificacion.ver", "notificacion.gestionar", "whatsapp.gestionar",
        "sync.ver", "sync.gestionar",
    ],
    # Bounded context de Inventario (granular; ver
    # backend/application/inventory/permissions.py). El workflow de
    # transferencias vive en TRANSFERENCIAS.*; Inventario sólo expone
    # `transito.ver` (lectura del stock en tránsito).
    "INVENTARIO": [
        "acceso", "ver", "ver.sucursal_propia", "ver.sucursales_asignadas",
        "ver.todas_sucursales", "ver.costo_referencia", "ver.trazabilidad",
        "ver.auditoria", "exportar", "trazabilidad.vincular",
        "almacen.ver", "almacen.crear", "almacen.editar", "almacen.activar",
        "almacen.bloquear", "almacen.desactivar",
        "ubicacion.ver", "ubicacion.gestionar",
        "movimiento.ver", "movimiento.crear_manual", "movimiento.reversar",
        "movimiento.sobrescribir", "movimiento.permitir_negativo",
        "lote.ver", "lote.crear", "lote.editar", "lote.bloquear", "lote.liberar",
        "lote.imprimir", "lote.reimprimir",
        "serie.gestionar",
        "reserva.ver", "reserva.crear", "reserva.liberar",
        "reserva.sobrescribir_asignacion",
        "transito.ver",
        "conteo.ver", "conteo.crear", "conteo.ejecutar", "conteo.confirmar",
        "conteo.recontar", "conteo.aprobar", "conteo.ver_esperado",
        "ajuste.ver", "ajuste.crear", "ajuste.aprobar", "ajuste.postear",
        "ajuste.reversar",
        "cuarentena.ver", "cuarentena.crear", "cuarentena.liberar",
        "cuarentena.disponer",
        "calidad.bloquear", "calidad.liberar",
        "peso.capturar", "peso.capturar_manual",
        "bascula.usar", "bascula.gestionar",
        "recepcion.ver", "recepcion.inspeccionar", "recepcion.reversar",
        "reposicion.ver", "reposicion.configurar", "reposicion.generar",
        "temperatura.ver", "temperatura.registrar", "temperatura.resolver",
        "configuracion.ver", "configuracion.editar",
        "notificacion.gestionar",
        "whatsapp.gestionar",
    ],
    "TRANSFERENCIAS": ["ver", "crear", "recibir", "cancelar"],
    # Bounded context de Productos / Product Master (granular; ver
    # backend/application/products/permissions.py). Los 4 códigos planos
    # originales (ver/crear/editar/eliminar) se conservan por compatibilidad
    # con roles ya sembrados (admin/gerente/almacen/cajero) — no autorizar
    # código nuevo contra ellos, usar ProductPermissions.
    "PRODUCTOS": [
        "ver", "crear", "editar", "eliminar",
        "acceso", "exportar",
        "ver.costo_referencia", "ver.interno", "ver.carnico", "ver.auditoria",
        "enviar_revision", "aprobar", "activar", "bloquear",
        "descontinuar", "archivar",
        "codigo.sobrescribir", "codigo.configurar_reglas",
        "categoria.ver", "categoria.gestionar",
        "marca.ver", "marca.gestionar",
        "atributo.ver", "atributo.gestionar", "variante.generar",
        "imagen.gestionar",
        "combo.ver", "combo.gestionar",
        "especie.ver", "especie.gestionar",
        "clasificacion_carnica.ver", "clasificacion_carnica.gestionar",
        "corte.ver", "corte.gestionar",
        "unidad.ver", "unidad.gestionar",
        "conversion.gestionar",
        "codigo_barras.gestionar", "codigo_alterno.gestionar",
        "receta.ver", "receta.crear", "receta.editar", "receta.aprobar", "receta.activar",
        "rendimiento.ver", "rendimiento.crear", "rendimiento.editar",
        "rendimiento.aprobar", "rendimiento.activar",
        "despiece.ver", "despiece.gestionar",
        "interno.ver", "interno.crear", "interno.editar", "interno.activar",
        "sucursal.ver", "sucursal.gestionar",
        "surtido.gestionar",
        "externo.buscar", "externo.importar", "externo.revisar", "externo.aprobar",
        "importacion.ejecutar", "importacion.aprobar",
        "configuracion.ver", "configuracion.editar",
        "notificacion.gestionar",
        "whatsapp.gestionar",
    ],
    # Bounded context de Customer Master (granular; ver
    # backend/application/customers/permissions.py). "ver", "crear",
    # "editar", "credito" se conservan por compatibilidad con
    # modulos/clientes.py (legacy) — no autorizar código nuevo contra ellos.
    "CLIENTES": [
        "ver", "crear", "editar", "credito",
        "acceso", "dashboard.ver", "buscar", "buscar.global",
        "configuracion.ver", "configuracion.editar",
        "ver.propia", "ver.equipo", "ver.sucursal", "ver.territorio",
        "ver.cartera", "ver.compania",
        "editar.propia", "editar.sensible",
        "activar", "desactivar", "suspender", "bloquear", "cerrar", "reabrir", "anonimizar",
        "contacto.ver", "contacto.crear", "contacto.editar", "contacto.eliminar",
        "contacto.verificar", "contacto.marcar_principal",
        "direccion.ver", "direccion.crear", "direccion.editar", "direccion.eliminar",
        "direccion.marcar_predeterminada",
        "fiscal.ver", "fiscal.editar", "fiscal.validar",
        "credito.ver", "credito.ver_resumen", "credito.ver_sensible",
        "credito.solicitar", "credito.revisar", "credito.aprobar", "credito.rechazar",
        "credito.limite.editar", "credito.limite.sobrescribir",
        "credito.suspender", "credito.bloquear", "credito.reabrir", "credito.cerrar",
        "credito.historial.ver", "credito.exportar",
        "consentimiento.ver", "consentimiento.capturar", "consentimiento.retirar",
        "consentimiento.evidencia.ver",
        "preferencia_comunicacion.ver", "preferencia_comunicacion.gestionar",
        "privacidad.solicitud.ver", "privacidad.solicitud.crear",
        "privacidad.solicitud.procesar", "privacidad.solicitud.aprobar",
        "sensible.ver", "sensible.exportar", "sensible.desenmascarar",
        "calidad.ver", "calidad.resolver",
        "duplicados.ver", "duplicados.revisar", "duplicados.descartar", "duplicados.fusionar",
        "importar", "importar.aprobar", "exportar", "actualizacion_masiva",
        "auditoria.ver",
        "elegibilidad_comercial.verificar",
        "pedidos.ver", "entregas.ver", "whatsapp.ver", "fidelidad.ver",
        "sync_conflictos.ver", "sync_conflictos.resolver",
    ],
    # Visibilidad del módulo nuevo (frontend/desktop/modules/customers_crm/),
    # adicional al legacy "CLIENTES" de arriba mientras ambos coexisten. Los
    # permisos granulares que el módulo usa internamente ya están
    # registrados bajo "CLIENTES"/"CRM" (CustomerPermissions/CRMPermissions);
    # esta entrada es solo la puerta de entrada al menú lateral.
    "CLIENTES_CRM": ["ver"],
    # Bounded context CRM (relación comercial: leads, oportunidades,
    # actividades, atención; granular, ver backend/application/crm/permissions.py).
    "CRM": [
        "leads.ver", "leads.ver.propia", "leads.ver.equipo",
        "leads.crear", "leads.editar", "leads.asignar", "leads.reasignar",
        "leads.calificar", "leads.descalificar", "leads.convertir",
        "leads.archivar", "leads.exportar",
        "oportunidades.ver", "oportunidades.ver.propia", "oportunidades.ver.equipo",
        "oportunidades.crear", "oportunidades.editar",
        "oportunidades.asignar", "oportunidades.reasignar",
        "oportunidades.cambiar_etapa", "oportunidades.sobrescribir_etapa",
        "oportunidades.marcar_ganada", "oportunidades.marcar_perdida",
        "oportunidades.reabrir",
        "pipeline.ver", "forecast.ver", "forecast.ver.equipo", "forecast.ver.compania",
        "actividades.ver", "actividades.crear", "actividades.editar",
        "actividades.completar", "actividades.cancelar", "actividades.reasignar",
        "tareas.ver", "tareas.crear", "tareas.asignar", "tareas.reasignar",
        "tareas.completar", "tareas.cancelar", "tareas.reprogramar",
        "notas.ver", "notas.crear", "notas.editar.propia", "notas.eliminar.propia",
        "notas.ver.privada", "notas.crear.privada",
        "recordatorios.crear",
        "casos.ver", "casos.ver.propia", "casos.ver.equipo",
        "casos.crear", "casos.editar", "casos.asignar", "casos.reasignar",
        "casos.escalar", "casos.resolver", "casos.cerrar", "casos.reabrir",
        "casos.ver.sensible",
        "sla.ver", "sla.gestionar", "sla.sobrescribir",
        "segmentos.ver", "segmentos.crear", "segmentos.editar",
        "segmentos.asignar", "segmentos.remover",
        "etiquetas.ver", "etiquetas.crear", "etiquetas.editar",
        "etiquetas.asignar", "etiquetas.remover",
        "territorios.ver", "territorios.gestionar",
        "carteras.ver", "carteras.gestionar", "carteras.asignar",
        "propietario.ver", "propietario.asignar", "propietario.reasignar",
        "bi.exportar",
        "automatizaciones.ver", "automatizaciones.crear", "automatizaciones.editar",
        "automatizaciones.activar", "automatizaciones.desactivar",
        "automatizaciones.ver_ejecuciones",
        "sync_conflictos.ver", "sync_conflictos.resolver",
    ],
    "MERMA": ["ver", "crear", "autorizar"],
    # Bounded context de Pedidos y Delivery / Order Management + Last-Mile
    # Fulfillment (granular; ver
    # backend/application/orders_delivery/permissions.py). Los 4 códigos
    # planos originales (ver/crear/asignar/entregar) se conservan por
    # compatibilidad con el gateo del botón "🛵 Delivery" del menú lateral
    # (interfaz/menu_lateral.py) — no autorizar código nuevo contra ellos,
    # usar OrdersDeliveryPermissions. Pedidos y Delivery comparten esta única
    # clave/entrada de navegación (master prompt §68: un solo sidebar
    # "PEDIDOS Y DELIVERY").
    "DELIVERY": [
        "ver", "crear", "asignar", "entregar",
        "acceso", "dashboard.ver",
        "ver.sucursal_propia", "ver.sucursales_asignadas", "ver.todas_sucursales",
        "exportar", "auditoria.ver", "alertas.ver", "analisis.ver",
        "pedido.crear", "pedido.editar_borrador", "pedido.confirmar",
        "pedido.programar", "pedido.reprogramar", "pedido.cancelar",
        "pedido.reversar",
        "preparacion.ver", "preparacion.asignar", "preparacion.iniciar",
        "preparacion.completar", "peso.capturar", "peso.sobrescribir",
        "sustitucion.proponer",
        "aprobacion_cliente.ver", "aprobacion_cliente.reenviar",
        "aprobacion_cliente.sobrescribir",
        "entrega.ver", "entrega.crear", "entrega.confirmar", "entrega.reversar",
        "repartidor.asignar", "ruta.planificar", "despacho.ejecutar",
        "llegada.confirmar", "falla.registrar", "reentrega.solicitar",
        "retorno_sucursal.registrar",
        "repartidor.ver", "repartidor.estado_gestionar", "repartidor.efectivo_ver",
        "cobro.registrar", "cobro.sobrescribir",
        "liquidacion.ver", "liquidacion.crear", "liquidacion.revisar",
        "liquidacion.aprobar", "liquidacion.cerrar",
        "configuracion.ver", "configuracion.editar",
        "notificacion.gestionar", "whatsapp.gestionar",
    ],
    # Bounded context de Compras (granular; ver backend/application/procurement/permissions.py).
    "COMPRAS": [
        "ver", "ver.sucursal_propia", "ver.sucursales_asignadas", "ver.todas_sucursales",
        "ver.costos", "ver.margenes", "ver.pagos", "ver.credito_proveedor", "ver.auditoria",
        "ver.analitica", "exportar",
        "directa.ver", "directa.crear", "directa.editar", "directa.confirmar",
        "directa.guardar_borrador", "directa.proveedor_ocasional", "directa.crear_producto",
        "directa.sobrescribir_precio", "directa.sobrescribir_costo", "directa.sobre_recibir",
        "directa.cancelar", "directa.reversar", "directa.imprimir",
        "pago.inmediato", "pago.caja_chica", "pago.tesoreria", "pago.transferencia",
        "credito_proveedor.usar", "anticipo.usar", "condiciones.mixtas",
        "limite.sobrescribir", "pago.ver_referencia",
        "solicitud.ver", "solicitud.crear", "solicitud.editar", "solicitud.enviar",
        "solicitud.aprobar", "solicitud.rechazar", "solicitud.cancelar",
        "rfq.crear", "rfq.enviar", "cotizacion.capturar", "cotizacion.editar",
        "cotizacion.comparar", "cotizacion.adjudicar", "cotizacion.sobrescribir_seleccion",
        "orden.ver", "orden.crear", "orden.editar", "orden.enviar_aprobacion",
        "orden.aprobar", "orden.enviar", "orden.confirmar", "orden.versionar",
        "orden.cancelar", "orden.cerrar",
        "recepcion.ver", "recepcion.crear", "recepcion.directa", "recepcion.completar",
        "recepcion.parcial", "recepcion.tolerancia", "recepcion.peso_manual",
        "recepcion.rechazar", "recepcion.reversar", "recepcion.cuarentena",
        "recepcion.devolucion", "calidad.inspeccionar", "calidad.liberar",
        "factura.ver", "factura.capturar", "factura.editar", "factura.conciliar",
        "factura.liberar_diferencia", "factura.bloquear", "factura.cancelar",
    ],
    # Compra en origen / logística de embarques (ver backend/application/logistics/authorization.py).
    "LOGISTICA": [
        "embarque.ver", "embarque.crear", "embarque.despachar", "embarque.forzar",
        "contenedor.gestionar", "contenedor.adjuntar", "contenedor.mover", "contenedor.sellar",
        "contenedor.liberar", "contenedor.escanear", "etiqueta.imprimir",
    ],
    "COTIZACIONES": ["ver", "crear", "aprobar", "convertir"],
    # Bounded context de Procesamiento Cárnico / Meat Processing (granular; ver
    # backend/application/meat_processing/permissions.py). Reutiliza la clave
    # histórica "PRODUCCION" (coincide con el botón del menú lateral,
    # interfaz/menu_lateral.py: "Procesamiento Cárnico" → "PRODUCCION") en vez de
    # introducir una clave paralela — una sola ruta canónica para la misma área
    # funcional (§3/§64 del prompt maestro de refactor).
    "PRODUCCION": [
        "acceso", "ver", "ver.sucursal_propia", "ver.sucursales_asignadas",
        "ver.todas_sucursales", "exportar", "ver.auditoria",
        "dashboard.ver",
        "preparacion.ver", "en_proceso.ver", "despiece.ver", "derivados.ver",
        "empaque_etiquetado.ver", "lotes_producidos.ver", "calidad.ver",
        "incidencias.ver", "trazabilidad.ver", "alertas.ver", "analisis.ver",
        "plan.ver", "plan.crear", "plan.editar", "plan.aprobar", "plan.cancelar",
        "orden.ver", "orden.crear", "orden.editar", "orden.aprobar",
        "orden.liberar", "orden.iniciar", "orden.pausar", "orden.reanudar",
        "orden.completar", "orden.cerrar", "orden.cancelar", "orden.reversar",
        "material.ver", "material.asignar", "material.sustituir",
        "consumo.capturar", "consumo.sobrescribir",
        "peso.ver", "peso.capturar", "peso.capturar_manual", "bascula.gestionar",
        "output.ver", "output.capturar", "output.coproducto.capturar",
        "output.subproducto.capturar", "output.derivado.capturar",
        "output.merma.capturar",
        "rendimiento.ver", "rendimiento.revisar", "rendimiento.aprobar",
        "rendimiento.sobrescribir",
        "reproceso.ver", "reproceso.crear", "reproceso.aprobar",
        "reproceso.ejecutar", "reproceso.cerrar",
        "empaque.ejecutar", "etiqueta.imprimir", "etiqueta.reimprimir",
        "configuracion.ver", "configuracion.editar",
        "notificacion.gestionar", "whatsapp.gestionar",
        # Sacrificio futuro (§37/§50) — feature-flagged, mismo bounded context.
        "sacrificio.acceso", "sacrificio.recepcion_animal",
        "sacrificio.lote_animal.gestionar", "sacrificio.orden.crear",
        "sacrificio.orden.aprobar", "sacrificio.ejecutar",
        "sacrificio.ante_mortem.registrar", "sacrificio.post_mortem.registrar",
        "sacrificio.canal.crear", "sacrificio.canal.clasificar",
        "sacrificio.decomiso.registrar", "sacrificio.enfriamiento.gestionar",
    ],
    "ETIQUETAS": ["ver", "imprimir"],
    "PLANEACION_COMPRAS": ["ver", "generar"],
    "FINANZAS_UNIFICADAS": ["ver"],
    # Bounded context financiero (nuevo). Los permisos de instrumentos
    # comerciales siguen §24 del contrato: nunca autorizar por nombre de rol.
    "FINANZAS": [
        "ver",
        "asiento.crear",
        "asiento.reversar",
        "periodo.cerrar",
        "periodo.reabrir",
        "cxc.ver",
        "cobro.crear",
        "cxp.ver",
        "pago.programar",
        "pago.autorizar",
        "pago.ejecutar",
        "tesoreria.ver",
        "tesoreria.transferir",
        "conciliacion.ver",
        "conciliacion.ejecutar",
        "presupuesto.ver",
        "presupuesto.aprobar",
        "activo.ver",
        "activo.capitalizar",
        "estados.ver",
        "commercial_obligation.read",
        "commercial_obligation.reconcile",
        "commercial_posting_profile.read",
        "commercial_posting_profile.manage",
        "commercial_adjustment.create",
        "commercial_adjustment.authorize",
    ],
    "ACTIVOS": ["ver", "crear", "mantenimiento"],
    "RRHH": ["ver", "crear", "editar"],
    # Bounded context de Fidelidad/Loyalty (granular; ver
    # backend/application/loyalty/permissions.py). El "ver" original se
    # conserva por compatibilidad con el gateo del botón "⭐ Fidelización"
    # del menú lateral — no autorizar código nuevo contra él, usar
    # LoyaltyPermissions. Cubre programas, membresías, puntos, niveles,
    # recompensas, retos, referidos, cumpleaños, retención, campañas,
    # cupones, vales y sorteos (master prompt §4 — todos comparten esta
    # entrada de navegación; Tarjetas de fidelidad tiene su propia clave
    # abajo, TARJETAS_FIDELIDAD, por ser un subdominio especializado).
    "GROWTH_ENGINE": [
        "ver", "acceso", "dashboard.ver", "auditoria.ver",
        "programa.ver", "programa.crear", "programa.editar",
        "programa.aprobar", "programa.activar", "programa.suspender",
        "membresia.ver", "membresia.inscribir", "membresia.suspender",
        "membresia.cerrar",
        "puntos.ver", "puntos.acreditar", "puntos.canjear", "puntos.ajustar",
        "puntos.reversar", "puntos.auditar",
        "nivel.ver", "nivel.gestionar",
        "recompensa.ver", "recompensa.gestionar", "recompensa.canjear",
        "reto.ver", "reto.gestionar",
        "referido.ver", "referido.gestionar", "referido.aprobar",
        "cumpleanos.ver", "cumpleanos.gestionar",
        "retencion.ver", "retencion.gestionar",
        "campana.ver", "campana.crear", "campana.aprobar", "campana.activar",
        "cupon.ver", "cupon.emitir", "cupon.canjear", "cupon.cancelar",
        "cupon.override",
        "vale.ver", "vale.emitir", "vale.canjear", "vale.recargar",
        "vale.cancelar", "vale.ajustar",
        "sorteo.ver", "sorteo.gestionar", "sorteo.sortear",
        "sorteo.boleto_imprimir", "sorteo.boleto_reimprimir",
        "antifraude.ver", "antifraude.gestionar",
        "configuracion.ver", "configuracion.editar",
    ],
    # Bounded context de Loyalty Cards (granular; ver
    # backend/application/loyalty_cards/permissions.py). Subdominio
    # especializado de Fidelidad (master prompt §30), con su propia entrada
    # de navegación ("💳 Tarjetas Fidelidad") y su propia clave — no
    # fusionar con GROWTH_ENGINE. El "ver" original se conserva por
    # compatibilidad.
    "TARJETAS_FIDELIDAD": [
        "ver", "acceso",
        "tarjeta.ver", "tarjeta.crear", "tarjeta.asignar", "tarjeta.activar",
        "tarjeta.bloquear", "tarjeta.reponer", "tarjeta.cancelar",
        "plantilla.ver", "plantilla.crear", "plantilla.editar",
        "plantilla.importar", "plantilla.aprobar", "plantilla.activar",
        "plantilla.archivar",
        "disenador.acceso", "formato.gestionar", "pliego.gestionar",
        "lote.crear", "lote.aprobar", "lote.imprimir",
        "reimprimir", "qr.rotar",
        "auditoria.ver", "configuracion.ver", "configuracion.editar",
    ],
    "INTELIGENCIA_BI": [
        "ver", "ver_ventas", "ver_inventario", "ver_compras", "ver_caja",
        "ver_clientes", "ver_proveedores", "ver_finanzas", "ver_merma",
        "exportar", "configurar",
    ],
    "WHATSAPP": ["ver"],
    "DISEÑADOR_TICKETS": ["ver"],
    "CONFIG_HARDWARE": ["ver"],
    "CONFIG_MODULOS": ["ver"],
    "CONFIG_SEGURIDAD": ["ver", "editar"],
    # SET-1: bounded context de Configuración/Settings (governance, empresa,
    # sucursales, estaciones, integraciones, feature flags, apariencia — ver
    # docs/refactor/settings_refactor_execution_plan.md). Los 3 stubs
    # CONFIG_HARDWARE/CONFIG_MODULOS/CONFIG_SEGURIDAD arriba se conservan
    # sin cambios porque interfaz/menu_lateral.py sigue gateando sus 3
    # botones actuales contra ellos; CONFIGURACION es la clave unificada
    # para la navegación consolidada objetivo (aún no wireada en el menú).
    "CONFIGURACION": [
        "ver", "ver_global", "ver_empresa", "ver_sucursal",
        "auditoria.ver", "exportar",
        "valor.crear", "valor.editar", "valor.enviar", "valor.aprobar",
        "valor.activar", "valor.rollback",
        "sensible.ver", "sensible.gestionar",
        "empresa.ver", "empresa.editar",
        "sucursal.ver", "sucursal.crear", "sucursal.editar", "sucursal.activar",
        "estacion.ver", "estacion.crear", "estacion.editar",
        "estacion.bloquear", "estacion.retirar",
        "integracion.ver", "integracion.crear", "integracion.editar",
        "integracion.probar", "integracion.activar", "integracion.desactivar",
        "integracion.secretos", "webhook.gestionar",
        "flag.ver", "flag.crear", "flag.editar", "flag.aprobar",
        "flag.activar", "flag.rollback",
        "apariencia.ver", "apariencia.gestionar",
        "tema.crear", "tema.aprobar", "tema.activar",
        # SET-23: bounded context de Offline (cache/expiración) — sección de
        # settings/, sin grupo de permisos propio, mismo criterio que
        # integracion.*/flag.*/apariencia.* arriba.
        "notificacion.ver", "notificacion.gestionar",
        "offline.ver", "offline.gestionar",
        # Usuarios/Roles/Auditoría — primera sección nueva más allá de los
        # 9 bounded contexts SET-0..23 originales, sobre la capa canónica
        # "FASE 6" (UserManagementService/RoleManagementService/
        # PermissionQueryService) que ya existía pero nunca tenía un
        # caller real. Desbloquear NO tiene código propio aquí — lo
        # gatea `UserSecurityService.unlock_user()` internamente contra
        # sus propios códigos ya existentes (CONFIG_SEGURIDAD.editar /
        # USUARIOS.desbloquear), mismo mecanismo que ya usaba la UI legacy.
        "usuario.ver", "usuario.crear", "usuario.editar", "usuario.activar",
        "rol.ver", "rol.crear", "rol.editar",
    ],
    # SET-1: bounded context de Device Management (dispositivos, perfiles,
    # asignación, diagnóstico — ver docs/refactor/settings_legacy_inventory.md §4).
    "DISPOSITIVOS": [
        "ver", "crear", "editar", "asignar", "probar", "deshabilitar",
        "diagnostico.ver", "configuracion.gestionar",
    ],
    # SET-1: bounded context de Document Output (plantillas, trabajos de
    # impresión, etiquetas, numeración — ver
    # docs/refactor/settings_legacy_inventory.md §5).
    "DOCUMENTOS": [
        "plantilla.ver", "plantilla.crear", "plantilla.editar",
        "plantilla.aprobar", "plantilla.activar",
        "trabajo.ver", "trabajo.crear", "trabajo.reintentar", "trabajo.cancelar",
        "reimprimir", "reimprimir_sensible",
        "etiqueta.ver", "etiqueta.crear", "etiqueta.editar",
        "etiqueta.aprobar", "etiqueta.activar", "etiqueta.imprimir",
        "etiqueta.reimprimir",
        "lote.imprimir", "precio.imprimir", "trazabilidad.imprimir",
        # SET-13 cutover: campañas de marketing en tickets.
        "campana.ver", "campana.crear", "campana.editar", "campana.activar",
    ],
    # SET-1: bounded context de Customer Display Management (pantalla del
    # cliente, contenido, campañas publicitarias — ver
    # docs/refactor/settings_legacy_inventory.md §6.4).
    "PANTALLA_CLIENTE": [
        "ver", "gestionar",
        "contenido.ver", "contenido.crear", "contenido.aprobar",
        "campana.programar", "publicidad.gestionar", "metricas.ver",
    ],
}


def normalize_permission(code: str) -> str:
    """Normalize permission codes so comparisons are case-insensitive."""
    return str(code or "").strip().upper()


def permission_code(module: str, action: str) -> str:
    """Build a canonical permission code using `MODULE.action` format."""
    return f"{str(module or '').strip().upper()}.{str(action or '').strip().lower()}"


def module_view_permission(module: str) -> str:
    """Return the canonical module visibility permission."""
    return permission_code(module, "ver")
