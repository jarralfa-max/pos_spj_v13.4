"""Identidad y versión de la aplicación.

Existe porque `version.py` estaba en la raíz del proyecto, fuera de las dos
únicas raíces válidas (§1). Los valores son los mismos; no se inventa ninguno.

Tras este cambio, `version.py` de la raíz se queda SIN NINGÚN consumidor —
`main.py` era el único. No se borra aquí: §0.5 exige preguntar antes de
eliminar un archivo, y un archivo huérfano no hace daño mientras tanto. Queda
anotado como pendiente de retirada.
"""

from __future__ import annotations

APP_NAME = "SPJ POS Enterprise"
VERSION = "13.4.0"
BUILD = "2026.03"
