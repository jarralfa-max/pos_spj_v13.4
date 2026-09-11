import os
import sys

# La raíz del proyecto tiene que ir PRIMERO en sys.path: `frontend` y `backend`
# son paquetes de nivel superior y se importan por su nombre.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from frontend.desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
