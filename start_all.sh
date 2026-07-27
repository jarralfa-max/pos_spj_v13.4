#!/bin/bash
# start_all.sh — Inicia POS SPJ + Microservicio WhatsApp en paralelo

set -e

echo "🚀 Iniciando SPJ POS v13.4 con Microservicio WhatsApp..."
echo ""

# Directorio del script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ── Microservicio WhatsApp ────────────────────────────────────────────────────
echo -e "${YELLOW}[1/2]${NC} Iniciando Microservicio WhatsApp en puerto 8000..."
cd whatsapp_service
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
WA_PID=$!
echo -e "${GREEN}✓${NC} Microservicio PID: $WA_PID"
cd ..

# Esperar a que esté listo
sleep 3
if ! kill -0 $WA_PID 2>/dev/null; then
  echo -e "${RED}✗ Microservicio falló al iniciar${NC}"
  exit 1
fi

# ── Aplicación Principal ──────────────────────────────────────────────────────
echo -e "${YELLOW}[2/2]${NC} Iniciando POS SPJ UI..."
cd pos_spj_v13.4
python main.py &
APP_PID=$!
echo -e "${GREEN}✓${NC} Aplicación PID: $APP_PID"

echo ""
echo -e "${GREEN}✅ Ambos servicios iniciados${NC}"
echo "   • POS SPJ:         http://localhost:5000 (UI PyQt5)"
echo "   • WhatsApp WA:     http://localhost:8000"
echo "   • Webhook handler: http://localhost:8000/webhook"
echo ""
echo "Presiona Ctrl+C para detener todos los servicios..."
echo ""

# Esperar a que ambos procesos terminen
wait $WA_PID $APP_PID

