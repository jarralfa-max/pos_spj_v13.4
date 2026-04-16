# Auditoría Fase Previa Obligatoria — POS/ERP SPJ v13.4

Fecha: 2026-04-16
Estado: Pre-implementación (sin cambios funcionales)
Metodología: PPP (Progress, Plans, Problems)

## 1) Análisis total del repositorio

### Estructura general
- Núcleo de aplicación PyQt en `pos_spj_v13.4/main.py` con bootstrap DB, integridad y carga de tema al arranque.
- Capas funcionales principales:
  - UI/módulos: `pos_spj_v13.4/modulos/*`, `pos_spj_v13.4/interfaz/*`, `pos_spj_v13.4/ui/*`.
  - Persistencia SQLite y compatibilidad: `pos_spj_v13.4/core/db/*`, `pos_spj_v13.4/database/conexion.py`.
  - Hardware: `pos_spj_v13.4/hardware/*`.
  - Servicios y sincronización: `pos_spj_v13.4/services/*`, `pos_spj_v13.4/sync/*`.
  - Migraciones y bootstrap: `pos_spj_v13.4/migrations/*`, `scripts/bootstrap_db.py`.

### Dependencias
- Stack principal PyQt5 + SQLite.
- Hardware: `pyserial`, `python-escpos`.
- BI/forecast: pandas, numpy, statsmodels, scikit-learn.
- Reportería: reportlab/openpyxl/fpdf2.
- Servicio WA/FastAPI en subárbol `whatsapp_service/`.

### UI
- Existe auditoría previa (`UI_AUDIT_REPORT.md`) con hallazgos de inconsistencia visual y subuso de estilos centralizados.
- Existe batería de pruebas por fases (fase 0 a fase 6) en `pos_spj_v13.4/tests/`.

### Servicios
- Inicialización central por `AppContainer` desde `main.py`.
- Hooks de webhook WhatsApp y verificador de versión.

### Configuración
- Tema se intenta cargar antes de mostrar ventanas (`load_saved_theme(None)` en arranque).
- Validaciones de BD y fallback de bootstrap contemplados.

### Hardware
- Cobertura de pruebas para guardas de hardware y `baud_rate` en fase 0.

### Persistencia
- Compatibilidad SQLite explícita; shim `database/conexion.py` mantiene imports legacy.
- Migraciones ejecutadas con `migrations/engine.py`.

---

## 2) Auditoría profunda obligatoria (estado actual)

### UI/UX
- Se confirma antecedente de deuda visual importante en `UI_AUDIT_REPORT.md` (botones, headers, cards, tooltips, uso parcial de estilos centralizados).
- En esta fase previa no se aplicaron cambios de UI todavía; queda para ejecución por fases.

### Temas
- El arranque ya intenta persistencia/aplicación temprana del tema (`main.py`), pendiente validar cobertura transversal por módulo.

### Sidebar (siempre oscuro)
- Existen pruebas dedicadas de menú lateral y whitelist en fase 0.

### Login
- Existen pruebas dedicadas de login UI en fase 0; pendiente validación visual manual del logo en runtime real.

### Módulos / importación
- Existen pruebas de sintaxis y wiring de fase 0 para menú/componentes; sin errores en ejecución de suite objetivo.

### Hardware
- Existen pruebas de guardas de hardware para evitar inicialización indebida y para configuración de `baud_rate`.

### Persistencia (tema/config)
- Hay cobertura de normalización de tema en fase 0 y bootstrap/migraciones.
- Persistencia funcional final de preferencias requiere validación E2E en entorno operativo con datos reales.

---

## 3) FASE 0 — Estabilización (verificación inicial por pruebas)

Estado de verificación local:
- `_toggle_canje` en ventas: cubierto y pasando en pruebas de fase 0.
- Whitelist menú lateral: cubierto y pasando.
- `piece_product_id` / consolidación de recetas: cubierto y pasando.
- Guardas hardware (`baud_rate`, init condicional): cubierto y pasando.
- UI components/login/theme normalization: cubierto y pasando.

Nota: error puntual `load_historial: no such column: r.nombre` y error de sintaxis en finanzas no fueron reproducidos en esta corrida focal; deben validarse con escenario funcional dirigido y/o test dedicado adicional.

---

## PPP (obligatorio)

## Progress
- Se completó análisis estructural de arquitectura, dependencias, UI, hardware y persistencia.
- Se ejecutó verificación técnica de Fase 0 con suites dedicadas (menú, ventas canje, login, tema, hardware, recetas, UI components).
- Se documentó el estado real y los huecos por validar en operación.

## Plans
1. Resolver preguntas críticas con negocio/operación (abajo) antes de tocar código funcional.
2. Ejecutar plan por fases con alcance acotado por entrega:
   - Fase 0: cerrar reproducibilidad de `load_historial` y finanzas con pruebas específicas.
   - Fase 1: estandarización de impresión ESC/POS, tokens UI, tooltips globales.
   - Fase 2: parser QR y flujo dual cliente/tarjeta con auditoría.
   - Fase 3+: motor financiero NIF/SAT, rentabilidad, BI, forecast y expansión.
3. Mantener retrocompatibilidad SQLite y trazabilidad de cambios (logs + pruebas + migraciones seguras).

## Problems
- Bloqueo de red para instalación de skills externas desde GitHub (HTTP 403 tunnel) en este entorno.
- Falta de respuestas de negocio para decisiones críticas de UX/operación/contabilidad (ver sección siguiente).
- No hay aún evidencia visual runtime (capturas) porque en esta entrega no se aplicó cambio de frontend.

---

## Preguntas críticas obligatorias (requieren respuesta para continuar)

1. **Prioridad operativa**: ¿confirmas que el orden de implementación debe iniciar por Fase 0 (bugs estabilización) y luego Fase 1, sin trabajo paralelo de Fase 2+?
2. **Criterio contable NIF/SAT**: ¿qué régimen fiscal y política de reconocimiento usar (devengado vs flujo) para el motor financiero?
3. **Catálogo contable**: ¿ya existe plan de cuentas maestro autorizado o debemos proponer uno base NIF con mapeo SAT?
4. **Sidebar oscuro fijo**: ¿debe ignorar completamente el tema global (claro/oscuro) y permanecer oscuro al 100% en todos los módulos?
5. **Tooltips globales**: ¿prefieres versión corta operacional o detallada con atajos de teclado y advertencias de impacto?
6. **Hardware**: confirma matriz por sucursal (báscula, impresora térmica, cajón, scanner) y valores válidos de `baud_rate` por dispositivo.
7. **Fallback de báscula**: ¿el ingreso manual de peso requiere bitácora de excepción obligatoria con motivo y usuario?
8. **Fidelización QR**: ¿cuál es el formato canónico de payload (ej. `LOYALTY:<id>`), y qué campos se deben ignorar del QR?
9. **Persistencia de preferencias**: ¿debe ser por usuario, por caja o por sucursal (o jerarquía combinada)?
10. **Módulos con botón sin UI**: comparte lista exacta de módulos afectados y ruta de reproducción por menú.
11. **Impresión/etiquetas**: ¿hay plantilla oficial de ticket/etiqueta validada por operación y marca (logo/QR/tamaño papel)?
12. **Auditoría**: ¿nivel de detalle requerido para bitácora (quién, cuándo, antes/después, terminal, sucursal, folio fiscal)?
13. **Criterio de éxito Fase 0**: ¿aceptas como "cerrado" cuando pasen tests + UAT guiado + evidencia de log?
14. **Ventana de despliegue**: ¿hay restricción horaria para rollout en sucursales activas?

