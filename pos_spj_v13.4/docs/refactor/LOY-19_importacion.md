# LOY-19 — Importación

Fecha: 2026-08-31
Alcance: master prompt §41-42 ("importación con saneamiento y validación de seguridad"), fase LOY-19.

## Decisión de alcance basada en lo que realmente está disponible

Antes de escribir código se verificó qué librerías de parseo de archivos existen en el entorno real (no se
asumió nada): `Pillow` y `defusedxml` sí están instaladas; `PyMuPDF`/`fitz`, `svglib`, `cairosvg`, `pypdf`,
`PyPDF2` y `lxml` NO. Esto define el alcance honesto de la fase:

- **PNG/JPEG**: soportado vía Pillow (`Image.open().verify()` + relectura real de dimensiones).
- **SVG**: soportado vía `defusedxml` (protección XXE nativa) + una allowlist propia de etiquetas/atributos
  peligrosos.
- **PDF**: explícitamente NO soportado — no hay ningún parser de PDF seguro instalado. La función levanta
  `InvalidCardDesignSchemaError` con un mensaje claro, nunca finge éxito.

## Por qué esto NO es "convertir el archivo a plantilla"

`import_canvas_dimensions()` deliberadamente NUNCA convierte el contenido vectorial/rasterizado de un
archivo en elementos declarativos (`TEXT`/`IMAGE`/`QR`/`BARCODE`/`SHAPE`, el vocabulario cerrado de LOY-18).
Hacerlo de forma genérica implicaría ejecutar lógica de renderizado contra un archivo controlado por un
atacante — exactamente lo que §41-42 prohíbe. Esta fase solo extrae el TAMAÑO DEL CANVAS de un archivo real
y validado; el `LoyaltyCardTemplateVersion` resultante tiene `elements: []` — un humano sigue poblando los
elementos reales en el Estudio (LOY-18) después. `ImportLoyaltyCardDesignUseCase` no delega en
`CreateLoyaltyCardTemplateVersionUseCase` (que exige `TEMPLATE_EDIT`) sino que construye la versión
directamente en su propia transacción, gateado por el permiso correcto y distinto `TEMPLATE_IMPORT` — mismo
principio de composición ya aplicado en toda la sesión (nunca enrutar a través de un caso de uso con el
permiso equivocado).

## Defensas de seguridad para SVG (más allá de XXE)

`defusedxml` resuelve XXE, pero no basta por sí solo — un SVG puede incluir `<script>`, atributos de evento
(`onload`, `onclick`, etc.) o referencias `href` a URLs remotas (`<image href="http://evil.example.com/...">`,
un vector real de exfiltración/SSRF si algún renderizador externo llega a resolverlas). Se agregó una
allowlist explícita que recorre TODOS los elementos del árbol XML ya parseado de forma segura y rechaza:
etiquetas `<script>`/`<foreignObject>`, cualquier atributo que empiece con `on`, y cualquier `href` que
apunte a `http://`/`https://`/`javascript:`/`data:text/html`.

## Dos bugs reales encontrados por tests, corregidos antes de reportar la fase lista

1. **Confusión de formato declarado vs. real, sin detectar**: el primer borrador de `_import_raster()`
   verificaba que el formato REAL del archivo (detectado por Pillow) fuera PNG o JPEG, pero nunca lo
   comparaba contra el formato DECLARADO por el llamador (`source_format`) — un JPEG real declarado como
   "PNG" pasaba sin error. Detectado por `test_declared_format_mismatch_rejected`. Corregido agregando un
   mapa `_DECLARED_TO_ACTUAL` y una verificación cruzada explícita.
2. (Heredado de LOY-18, reconfirmado aquí): la disciplina de "probar con una entrada adversarial real, no
   solo el caso feliz" se aplicó desde el principio en esta fase — los tests de SVG incluyeron XXE,
   `<script>`, atributos `on*`, `href` remoto y `<foreignObject>` desde el primer intento, precisamente
   porque LOY-18 ya había mostrado que una validación "razonable a primera vista" puede tener huecos reales.

## Qué se construyó

`backend/infrastructure/loyalty_cards/design_import.py` (`import_canvas_dimensions()`) — vive en
`infrastructure/`, no en `domain/`, porque depende de librerías externas (Pillow, defusedxml); mismo criterio
de capas que el resto del proyecto. `backend/application/loyalty_cards/use_cases/import_use_cases.py`
(`ImportLoyaltyCardDesignUseCase`, permiso `TEMPLATE_IMPORT`).

## Alcance honesto

- PDF: no soportado, señalado explícitamente, no fingido.
- Límite de archivo: 10 MB fijo (defensa básica contra archivos anormalmente grandes) — no hay límites
  configurables por instalación todavía.
- El "import" de SVG solo extrae `viewBox` para el tamaño; no valida más allá de la allowlist de seguridad
  (p. ej. no rechaza SVGs con miles de nodos que podrían ser costosos de parsear — sin límite explícito de
  profundidad/nodos en esta fase).

## Tests

24 tests nuevos (`test_design_import.py`: 19; `test_import_use_cases.py`: 5), todos pasando tras la
corrección del bug de formato declarado vs. real. 446 tests de todo el dominio Fidelidad/Comercial/Sorteos/
Tarjetas corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-20 (Pliegos 12×18): usar las dimensiones de canvas ya validadas para calcular imposición real.
- Soporte de PDF: requiere agregar una librería de parseo segura (p. ej. `pypdf`) al entorno — trabajo de
  infraestructura futuro, no de esta fase.
