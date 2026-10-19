# Báscula POS — Rhino BAR-8RS USB

## Fuente de configuración
El usuario confirmó BAR-8RS y que su configuración proviene del módulo
Configuración. El POS consulta Device Management; no fija COM ni velocidad
en la UI. El perfil USB ahora conserva los parámetros serie cuando se aportan.
Una conexión USB con puerto virtual COM también puede registrarse como SERIAL.

`ScaleConfigurationQuery` exige POS.bascula.usar y alcance de sucursal.
Con estación explícita usa su asignación SCALE y comprueba que esté activa en
esa sucursal. Sin estación sólo acepta una báscula activa inequívoca.
Al volver a mostrar el POS se vuelve a resolver su configuración.

## Protocolo
El adaptador Rhino solicita peso con P (ASCII 80). Acepta exclusivamente tramas
completas de peso decimal y unidad, con prefijo ST/US opcional. Rechaza texto
arbitrario, cifras múltiples de precio/importe y unidades desconocidas.
El número de puerto, baud rate, paridad, bits y timeout provienen del perfil.
La estabilidad de una trama sin marcador requiere muestras consecutivas coherentes;
es estabilidad observada, no una garantía adicional del fabricante.

Fuentes consultadas:
- [Rhino: BAR-8RS USB](https://www.rhino.mx/producto/bascula-electronica-multifunciones-40-kg-con-puerto-usb/).
- [Manual del fabricante distribuido por Ferremobil](https://ferremobil.com/pdf/_001/21BAS016430_001.pdf).
La descarga del enlace de manual del fabricante redirigió a autenticación.
El formato físico devuelto por ESTA unidad todavía no se ha capturado. El parser
es deliberadamente estricto: un formato no reconocido produce error y permite
captura manual explícita; no extrae un número arbitrario de la respuesta.

## Contrato y seguridad
- Peso Decimal; conversión explícita de kg/g/lb/oz. Pricing decide el precio,
  incluyendo contexto de venta/cliente/cantidad; la UI sólo formatea el importe.
- `ScaleReadingService` nunca recibe el carrito. Una venta con 6.500 kg no cambia
  la lectura actual de 0.850 kg en ninguna de las dos pantallas.
- Lecturas inestables, vencidas, futuras, sin zona horaria y no finitas no se aceptan.
  Cero es una lectura real visible; el dominio rechaza agregar cantidad cero.
- La vigencia se resuelve por `sales.scale_stale_seconds` en monitor y casos de uso.
- Al fallar conexión se retira la lectura actual. El historial no se usa para cobrar.
- La invalidación descarta muestras que estaban en vuelo. El worker no toca SQLite
  ni widgets; Qt entrega snapshots al hilo de UI.
- Agregar y actualizar requieren lectura vigente que coincida con la cantidad,
  además de permisos. La entrada manual queda diferenciada como MANUAL.
- Rhino/SICS entregan neto en los formatos soportados; no se envían comandos de
  tara/cero ni se presenta una tara física desconocida como medida por el equipo.
  Las pruebas de servicio incluyen lectura con tara conocida de 0.200 kg.

## Evidencia y pendientes
La enumeración de puertos de este entorno devolvió una lista vacía. No se afirma
conexión ni calibración física. Pruebas simuladas: parser estricto, estabilidad,
cero, tara, caducidad, desconexión, invalidación, cantidad discrepante y edición;
perfil USB persistido mediante repositorio real en SQLite de prueba.

Aceptación con equipo: abrir Configuración, verificar perfil y asignación; confirmar
COM/velocidad del fabricante; leer plato vacío, 0.850 kg y peso variable; probar
desconexión/reconexión y captura manual. Comparar neto con el visor físico y confirmar
trama recibida antes de dar por certificado el controlador.
