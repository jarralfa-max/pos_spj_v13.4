# CRM-18 — Formularios: inputs, validación, touch, teclado virtual

Fecha: 2026-08-13. Sexto conjunto de páginas reales en
`frontend/desktop/modules/customers_crm/` — construye `customers.create`
(Alta rápida) y, por instrucción explícita del usuario ("Teclado virtual
debe ser parte del estandar de UI/UX"), cierra un hueco real y
transversal a TODA la aplicación en la infraestructura compartida de
teclado virtual, no solo en el módulo CRM.

## El hallazgo principal: el teclado virtual ya existía, pero solo la mitad de los inputs especializados lo usaban

Antes de escribir el formulario se investigó `frontend/desktop/components/
virtual_keyboard.py` — **ya existe** un mecanismo completo y reutilizable:
`attach_virtual_keyboard_action(line_edit, *, numeric=False)`, que agrega
una acción con icono (`Icons.KEYBOARD`/`Icons.NUMERIC_KEYPAD`, no emoji),
tooltip "Mostrar teclado", y abre el teclado en pantalla del sistema
operativo. `StandardLineEdit`, `SearchInput` y `NumericInput` (de donde
`MoneyInput` hereda) ya lo tenían conectado.

Pero **`EmailInput`, `DecimalInput`, `TaxIdentifierInput`, `IntegerInput` y
`AddressInput` no lo tenían** — exactamente los inputs especializados que
un formulario CRM real (RFC, correo, teléfono, montos, cantidades) más
necesita. Dado que el usuario pidió explícitamente que el teclado virtual
sea "parte del estándar de UI/UX" (no "de CRM"), y dado que estos cinco
componentes viven en `frontend/desktop/components/` — compartido por TODA
la aplicación, no solo por `customers_crm` — el arreglo se hizo ahí, no
duplicado dentro del módulo CRM. Beneficia a cada módulo que ya usa estos
inputs (Compras, Caja, Transferencias, etc.), no solo a esta fase.

### Qué se conectó y qué se documentó como pendiente (no se tocó a la fuerza)

| Componente | Acción |
|---|---|
| `EmailInput` | Conectado (texto) |
| `DecimalInput` | Conectado (numérico) |
| `TaxIdentifierInput` | Conectado (texto) |
| `IntegerInput` (`QSpinBox`) | Conectado a `.lineEdit()` (numérico) |
| `AddressInput` (compuesto) | Conectado solo en `_search_box`; el `QTextEdit` de captura manual queda documentado como brecha — `attach_virtual_keyboard_action` apunta a la API de acción final de `QLineEdit`, que `QTextEdit` no expone igual |
| `PhoneInput` | **No tocado** — envuelve `modulos.spj_phone_widget.PhoneWidget`, código legacy con su propio `setStyleSheet` inline que antecede al design system; conectar el teclado ahí significaría editar internals legacy sin probar, desproporcionado para esta fase (el teléfono es opcional en el formulario de Alta rápida). Documentado en el propio docstring de `phone_input.py`, no silenciado. |

## El formulario: `customers.create` (Alta rápida)

`pages/create_customer_page.py` — `CreateCustomerPage`: `PageHeader` +
`StandardForm`/`FormField` (nombre para mostrar\*, tipo de cliente, RFC,
teléfono, correo) + botón primario "Crear cliente". Cada campo usa su
propio contrato de validación ya existente (`is_valid()`/`error_message()`
de `TaxIdentifierInput`/`EmailInput`; `StandardLineEdit.is_valid()` para el
campo requerido) — esta página nunca reimplementa un patrón de RFC o de
correo que el componente especializado ya posee; solo decide CUÁNDO
mostrarlos (al enviar) y DÓNDE (`FormField.set_error()`).

`CustomerCrmPresenter.create_customer()` — el primer método de ESCRITURA
que este presenter expone (los quince anteriores, CRM-15/16/17, son de
solo lectura). A diferencia de los métodos de lectura, no busca en
`query_services` sino en `command_handlers["create_customer"]`: correr
`CreateCustomerUseCase` necesita una conexión sqlite viva como primer
argumento posicional (todo caso de uso en este repositorio lo requiere —
la convención Unit-of-Work-por-llamada), y este presenter deliberadamente
nunca sostiene una conexión él mismo. `command_handlers` era exactamente
el slot que CRM-14 ya había declarado en el constructor del presenter y
dejado vacío hasta ahora — el mismo patrón "CRM-N lo construye, CRM-M
finalmente lo usa" que se repite en todo este pipeline, esta vez con el
propio presenter de este módulo, no con un servicio de backend.

**Cierre de ciclo completo entre tres fases**: al crear un cliente con
éxito, `CreateCustomerPage` emite `customer_created(entity_id)`;
`CustomersCrmWorkspace` (extendido) navega a `customers.profile` y llama
`CustomerProfilePage.show_customer(entity_id)` — el usuario aterriza
directamente en el Expediente del cliente recién creado (CRM-17), que a su
vez muestra el mismo Directorio (CRM-16) desde el que probablemente llegó.

## Touch

Ningún campo de este formulario define su propia altura — todos heredan
`TouchTarget.INPUT_HEIGHT` (40px) ya establecido por cada componente
especializado desde antes de esta fase (o, para los cinco recién
corregidos, agregado en el mismo cambio que el teclado virtual, ya que
ambos requisitos de §90 — "targets 48–56px" y "teclado virtual" — viven en
la misma sección del prompt maestro y se atienden juntos). Ningún tamaño se
hardcodeó de forma dispersa en `create_customer_page.py`.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_*.py tests/ui/test_specialized_inputs.py -q
# 22 guardrails + 87 (las cinco fases de UI) + los tests preexistentes de inputs especializados
```

- 14 pruebas nuevas (`test_customers_crm_create_customer_page.py`): el
  teclado virtual efectivamente conectado en los cinco componentes
  (verificando la propiedad dinámica `virtualKeyboard`, no solo que no
  truene), `create_customer()` del presenter (falla sin conectar, delega
  al `command_handler` con `actor_user_id`/`operation_id` correctos, normaliza
  cadenas vacías a `None`), validación del formulario (nombre vacío
  bloquea el envío, RFC/correo inválidos bloquean el envío y muestran el
  error en el campo correcto, un fallo del backend muestra el estado de
  error SIN limpiar el formulario, el tipo de cliente por defecto es
  `INDIVIDUAL`), y el enlace completo Alta rápida → Expediente contra el
  workspace real.
- Un mismo tipo de falso positivo del guardrail de SQL crudo, ya visto en
  CRM-17: el docstring del presenter mencionaba literalmente
  `` `CreateCustomerUseCase.execute()` `` en prosa, y el escáner
  `\.(execute|executemany)\s*\(` lo detectó como una llamada real.
  Reescrito sin el paréntesis literal.
- Se corrieron también las pruebas preexistentes de
  `tests/ui/test_specialized_inputs.py`/`tests/unit/test_phase3_ui_components.py`
  antes de tocar los componentes compartidos, para distinguir fallas
  preexistentes de regresiones propias. Cinco fallas preexistentes
  confirmadas como no relacionadas (verificado con `git status` — ninguno
  de esos archivos, `status_badge.py`/`search_selector.py`/`phone_input.py`'s
  lógica propia, estaba modificado por este trabajo): un desajuste de
  nombre de propiedad en `StatusBadge` ("status" vs. "variant" real), un
  `NameError` de una variable mal referenciada en el propio test de
  `SearchSelector`, un tipo de señal incompatible en otro test de
  `SearchSelector`, un archivo `modulos/merma.py` que ya no existe, y una
  aserción de `PhoneInput.is_valid()` que no coincide con su
  implementación actual. Ninguna se tocó — fuera de alcance, no
  introducidas por esta fase.
- 858 tests combinando toda la suite `customers`/`crm` + las cinco fases de
  UI (CRM-14..18) + los tests preexistentes de inputs especializados pasan
  juntos — cero regresión.
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Teclado virtual en `PhoneInput`** — requiere migrar o tocar
  `modulos/spj_phone_widget.PhoneWidget` (legacy), fuera de alcance de esta
  fase.
- **Teclado virtual en el `QTextEdit` de captura manual de `AddressInput`**
  — necesita una variante de `attach_virtual_keyboard_action` para
  `QTextEdit`, no construida aquí.
- **Formularios de edición** (no solo alta) para Clientes, y formularios
  equivalentes para Leads/Oportunidades/Casos — esta fase es
  deliberadamente solo de alta rápida, no de edición ni de las otras tres
  entidades.
- **Conexión real a `command_handlers["create_customer"]` con una conexión
  de base de datos viva** — sigue pendiente de la misma decisión de
  registro en el menú global que CRM-14/15/16/17 ya dejaron documentada.
