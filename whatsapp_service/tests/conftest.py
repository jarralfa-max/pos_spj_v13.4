import sys
from pathlib import Path

# Ensure whatsapp_service package-relative imports (flows/, parser/, config/) work
# regardless of pytest collection order.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
