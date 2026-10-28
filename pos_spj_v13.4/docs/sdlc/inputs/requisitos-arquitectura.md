# SPJ ERP — Requisitos de la arquitectura objetivo

Documento de referencia. Claude Code lo consulta cuando una tarea toca estos temas; no hace falta pegarlo en el chat.

## 1. Auditoría inicial (Fase 1)

Inspecciona: estructura del repo, rama y estado Git, aplicación de escritorio y punto de entrada, base SQLite, autenticación, permisos, módulos, contextos de dominio, servicios, endpoints, migraciones, sincronización, instaladores, actualizador, pruebas y documentos de arquitectura.

Audita en particular la integración de Cash Register: caja, cajones, turnos, ventas, devoluciones, movimientos, cortes, inventario, compras, logística, almacenes, planta, finanzas y contabilidad. Revisa cómo se resuelve el turno activo y localiza cualquier proveedor, servicio o pantalla que use una fuente de estado distinta.

Verifica la implementación real de PostgreSQL y FastAPI. Busca `NotImplementedError`, `pass`, `TODO` y stubs; la existencia de abstracciones o documentos no significa soporte funcional.

**Entregable:** `docs/spj/auditoria/matriz-hallazgos.md` con cada elemento clasificado como: implementado y probado · parcialmente implementado · documentado pero no implementado · defectuoso · duplicado · pendiente. Cada fila lleva ruta de archivo y evidencia verificable (línea, resultado de prueba o comando). Después, un plan por etapas en `docs/spj/auditoria/plan-por-etapas.md`. Sin cambios de código en esta fase.

## 2. Arquitectura objetivo

Arquitectura híbrida offline-first para Windows 10/11:

- **A.** Aplicación de escritorio SPJ ERP con módulos compartidos y acceso condicionado por permisos.
- **B.** SQLite local por terminal para operación offline, datos locales, borradores y cola de salida persistente.
- **C.** Servicio local de sucursal en una computadora Windows existente, para coordinar recursos compartidos entre terminales sin internet (caja, turno y otros que requieran consistencia).
- **D.** API central FastAPI + PostgreSQL para servicios corporativos, sincronización, datos consolidados y coordinación entre sucursales.
- **E.** Clientes que hablan solo con servicios autorizados, nunca directo con PostgreSQL.
- **F.** Transporte seguro, autenticación entre servicios, configuración protegida, respaldos y observabilidad.

Reutiliza los componentes actuales que ya cumplan alguna de estas responsabilidades y documenta cada decisión.

## 3. Usuarios, roles y permisos

Separa: identidad de usuario, sesión de autenticación, roles, permisos, asignaciones de acceso, ámbito organizacional, terminal y recurso operativo.

- Un rol es un conjunto configurable de permisos; su nombre no concede privilegios.
- Un usuario puede tener varios roles y asignaciones.
- El acceso se configura por rol y por usuario. Respeta la precedencia existente o, si no existe, propón una política inequívoca y espera aprobación antes de cambiarla.
- Los permisos distinguen módulo, acción, recurso, ámbito y condiciones.
- La autorización se verifica en backend en cada operación; la UI solo refleja permisos efectivos.
- Cambiar de usuario renueva contexto y permisos sin heredar la sesión anterior.
- Mínimo privilegio, denegación por defecto, auditoría y validación de alcance.
- No borres ni restablezcas la configuración actual de roles y permisos durante la migración.

Documenta una matriz de permisos para perfiles de referencia (cajero, supervisor de caja, gerente, logística, compras, almacén, producción, finanzas, administración). Son perfiles de análisis: no los crees automáticamente ni concedas privilegios sin aprobación. Los permisos finales se derivan de la configuración existente y de una política aprobada.

## 4. Ámbitos organizacionales y módulos

Modela los ámbitos según las entidades reales: empresa, territorio, sucursal, planta, almacén, centro operativo, terminal, caja, cajón, turno, etc. No fuerces a todos los módulos a tener sucursal activa.

- **POS:** terminal asignada persistentemente a una sucursal y, si aplica, a caja/cajón. Ventas y movimientos conservan el ámbito de origen.
- **Logística:** opera transversalmente entre sucursales, almacenes, rutas y destinos sin sucursal activa artificial; cada operación identifica origen, destino y ámbito real.
- **Compras:** usa los ámbitos y centros autorizados del dominio existente.
- **Almacén y producción:** separa almacenes, plantas y centros de operación de las sucursales cuando corresponda.
- **Gerencia y finanzas:** consultas globales o segmentadas solo dentro de sus permisos.
- **Administración:** configura el sistema con privilegios explícitos y auditables.

Esta lista es conceptual: primero descubre los módulos reales y no dupliques bounded contexts ni entidades.

## 5. Instalación y visibilidad de módulos

Una sola aplicación con todos los módulos de negocio necesarios; no una versión por rol. El usuario solo ve y usa lo autorizado. Tener el módulo instalado nunca concede autorización.

Perfiles de despliegue: terminal POS, terminal administrativa, servicio local de sucursal, servidor central. Reutilizan artefactos comunes; no todos los servicios corren en todas las máquinas.

Cada terminal registrada tiene: `terminal_id` único y persistente, tipo, ámbito asignado, estado, versión de app, versión de esquema y versión de protocolo de sincronización. La sucursal de una terminal POS no se cambia desde el login ni por edición local no autorizada.

## 6. Login y acceso entre sucursales

Al iniciar sesión valida identidad, estado de cuenta, asignaciones, permisos, estado del dispositivo y ámbito. El ámbito del POS debe coincidir con el autorizado para terminal y usuario.

- Usuario de A en POS de B sin asignación válida → acceso operativo denegado, con motivo explicado.
- Usuario asignado a A y B → solo módulos y operaciones permitidos en el ámbito activo.
- Cuenta corporativa con consultas globales → no obtiene automáticamente acceso operativo al POS de otra sucursal.
- Nunca cambiar la sucursal silenciosamente al iniciar sesión.
- Registrar, suspender, revocar o reasignar terminales requiere autorización, auditoría y manejo seguro de datos pendientes.
- Terminal nueva o suspendida no hace operaciones productivas hasta estar registrada y autorizada.

## 7. Varios usuarios en una máquina

Inicios de sesión secuenciales en una instalación compartida, cada uno con sesión, permisos y contexto propios.

Al cerrar sesión: limpiar credenciales, cachés de autorización y contexto sensible; no cerrar la caja ni revertir operaciones confirmadas; bloquear pantalla cuando corresponda. Borradores y operaciones abiertas quedan aislados y no se atribuyen al siguiente usuario. Transferir una operación pendiente requiere flujo explícito, permiso y auditoría.

Cada acción registra actor real, terminal, ámbito, recurso, fecha, resultado e identificador de operación. Nunca una sesión global compartida.

## 8. Cajas y turnos compartidos entre terminales

Caja y turno son recursos operativos compartidos. Un gerente autorizado puede consultar desde otra terminal la misma caja y el mismo turno abierto por el cajero, sin abrir otra caja ni otro turno.

- Una única fuente canónica del turno activo; todas las pantallas y servicios la usan. Elimina fuentes contradictorias y fallbacks silenciosos solo después de auditar a sus consumidores reales.
- Permisos separados: consultar, vender, abrir turno, suspender, reanudar, registrar movimientos, contar efectivo, revisar, aprobar, cerrar. Consultar no concede operar.
- Conserva al responsable original y la trazabilidad de cada movimiento. Distingue saldo esperado de efectivo contado.
- Transiciones de estado validadas en dominio/aplicación/backend, no en botones.
- Impide dos turnos incompatibles para la misma caja/cajón según la regla de negocio vigente.
- Integra ventas, devoluciones, caja, tesorería y finanzas mediante contratos o eventos de dominio, sin escrituras directas entre bounded contexts.
- Control de concurrencia contra doble cierre, movimientos repetidos y estados inconsistentes.

## 9. Operación offline y servicio local

SQLite permite seguir operando sin internet dentro de las políticas aprobadas. Sin internet, una terminal no finge conocer operaciones recientes de otras máquinas.

Si varias terminales comparten caja, turno o inventario durante una caída de internet, se requiere red local y un servicio de sucursal que coordine; SQLite por terminal no basta. Evalúa si una computadora Windows existente puede alojarlo con respaldo, disponibilidad y seguridad adecuados.

Si también cae el servicio local, cada terminal solo ejecuta operaciones offline que puedan registrarse sin violar invariantes. Las que requieren coordinación se bloquean o limitan explícitamente. Define procedimientos para reconexión, resolución de pendientes y fallo del anfitrión local.

## 10. SQLite, FastAPI, PostgreSQL y sincronización

- SQLite local = almacenamiento offline; FastAPI = frontera de servicio; PostgreSQL central = datos consolidados y autoridad central. PostgreSQL nunca expuesto a internet.
- Cola de salida persistente, identificadores globalmente únicos, reintentos seguros, idempotencia en servidor, estados de sincronización, versionado, deduplicación, auditoría y manejo de conflictos.
- Reenvío por timeout, doble clic, reinicio o recuperación de red nunca produce una segunda venta o movimiento.
- Autoridad definida por entidad y tipo de operación. Nada de "gana el último" para inventario, caja, turnos o contabilidad. Conflictos visibles, resueltos con reglas deterministas y auditables.
- Contrato API y protocolo de sincronización versionados. Autenticación y autorización servicio a servicio. Respaldos, recuperación y supervisión.
- PostgreSQL no se declara funcional sin adaptador real, migraciones compatibles y pruebas de integración.

## 11. Login y autorización offline

Con conexión: valida cuenta, permisos y asignaciones contra el servicio autorizado. Sin conexión: solo identidades y permisos offline previamente autorizados, guardados de forma segura, con vigencia limitada y operaciones permitidas definidas.

Define el tratamiento de: revocaciones ocurridas con la terminal desconectada, expiración de credenciales, cambios de rol, pérdida de dispositivo y operaciones de alto riesgo. Nunca mantener privilegios indefinidamente ni elevarlos por falta de servidor. Explicar al usuario cuando una acción se bloquea por política offline. Al reconectar, sincronizar y revalidar sin atribuir operaciones al usuario actual si las hizo otro.

## 12. Duplicados y concurrencia

- Identificador estable por operación de negocio; claves de idempotencia en escrituras críticas; restricciones de unicidad en BD cuando aplique. Deshabilitar botones no basta.
- Transiciones y actualizaciones concurrentes controladas con transacciones, versiones o equivalente.
- Estados: borrador, pendiente, confirmada, rechazada, compensada.
- Nunca borrar trazabilidad para ocultar un duplicado; usar reversa/compensación autorizada.

## 13. Instalación y actualización seguras

- Instalador Windows que conserva datos, configuración y rutas persistentes. Registro seguro de terminal y perfil. Sin secretos incrustados ni en texto plano.
- Actualizaciones: verificar firma e integridad, compatibilidad de versiones, respaldar SQLite y configuración, migrar con el mecanismo oficial, validar resultado y ofrecer recuperación.
- No borrar cola de sincronización, identidad de terminal, asignación de sucursal ni permisos.
- Sucursales offline pueden actualizar sin quedar incompatibles. Política de versiones mínimas, compatibilidad de API/protocolo y ventana de despliegue. Sin actualizaciones simultáneas forzadas ni migraciones destructivas sin respaldo, plan de recuperación y pruebas.

## 14. Seguridad y auditoría

Mínimo privilegio, validación de ámbito en backend, sesiones seguras, secretos protegidos, cifrado donde corresponda, control de acceso a la red local, límites de reintentos y registro de eventos de seguridad. La terminal no puede alterar su sucursal ni sus privilegios.

Registrar: autenticaciones, cambios de permisos, registro/revocación de terminal, operaciones de caja, sincronización, conflictos, actualizaciones y acciones administrativas — quién, qué, cuándo, terminal, ámbito, id de operación y resultado. Nunca contraseñas, tokens ni secretos.

## 15. Pruebas de aceptación

Unitarias, integración y extremo a extremo para:

- Usuario de A operando POS de B sin autorización → denegado.
- Usuario asignado a A y B → limitado a permisos y ámbito activo.
- Logística transversal sin sucursal activa artificial.
- Módulo instalado pero no autorizado → inaccesible desde UI y API.
- Dos usuarios secuenciales en una terminal → sin herencia de sesión ni permisos.
- Cajero abre turno en terminal A; gerente autorizado consulta el mismo turno en terminal B.
- Dos terminales con recursos compartidos por el servicio local → sin turnos duplicados.
- Doble clic, reintentos, timeout, reinicio y sincronización repetida → una sola operación lógica.
- Dos usuarios confirman/cierran simultáneamente → invariantes respetadas.
- Cae y vuelve internet; cae el servicio local; la terminal reinicia → la cola persiste.
- Permiso revocado con terminal offline → se aplica la política de vigencia.
- Actualización exitosa, fallida y rollback → datos y pendientes preservados.
- Migración SQLite y PostgreSQL → integridad, respaldos y recuperación.
- Auditoría de acciones, alcance y actor real.

Ninguna prueba que solo compruebe que una pantalla abre cuenta como aceptación.

## 16. Plan de entrega

| Fase | Contenido | Entregables en `docs/spj/` |
|---|---|---|
| 1 | Auditoría verificable y matriz de funcionalidades | `auditoria/matriz-hallazgos.md`, `auditoria/plan-por-etapas.md` |
| 2 | Especificaciones aprobables: arquitectura, permisos/ámbitos, instalación/actualización, auth offline, sincronización, caja compartida | `specs/*.md` |
| 3 | Plan de migración compatible y pruebas de regresión | `migracion/plan.md` + pruebas de regresión en verde |
| 4 | Implementación incremental, primero los defectos que bloquean la arquitectura | Código + pruebas por incremento |
| 5 | Piloto: 2 terminales Windows, 2 usuarios, 1 caja compartida; luego sucursal y servidor central | `piloto/resultados.md` |
| 6 | Ampliación progresiva al resto de sucursales | `despliegue/*.md` |

## 17. Documentación final

Diagramas (Mermaid) de: despliegue, login, cambio de usuario, venta offline, consulta de caja compartida, sincronización y actualización. Matriz roles/permisos/ámbitos, catálogo de módulos, inventario de servicios, configuración por perfil de terminal, política de conflictos, política offline, plan de respaldo/recuperación, matriz de compatibilidad de versiones, guía de instalación Windows, inventario de decisiones y riesgos, instrucciones de desarrollo y producción, pruebas reproducibles y procedimiento de recuperación. Nada se declara desplegado o probado si no se ejecutó.

## Objetivo final

Una aplicación SPJ ERP común con módulos sujetos a permisos, usuarios independientes de terminales, ámbitos correctos para POS y logística, cajas y turnos compartidos, operación offline controlada, sincronización sin duplicados, servicio local de coordinación, FastAPI y PostgreSQL centrales, instalador y actualizador seguros, y conservación de las funciones y configuraciones existentes.
