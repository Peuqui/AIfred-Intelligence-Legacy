#!/bin/bash
#
# AIfred Intelligence - Python Environment Setup
# Erstellt venv und installiert Python-Dependencies
#

set -e  # Exit on error

echo "=================================================="
echo "  AIfred Intelligence - Python Setup"
echo "=================================================="
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "📂 Projekt-Verzeichnis: $PROJECT_DIR"
echo ""

# Check if running with sudo (should NOT be run with sudo)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}❌ Dieses Script sollte NICHT mit sudo ausgeführt werden!${NC}"
    echo "   Führe es als normaler User aus: ./scripts/setup-python.sh"
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 ist nicht installiert${NC}"
    echo "   Installiere mit: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ $PYTHON_VERSION gefunden${NC}"
echo ""

# Create venv if it doesn't exist
VENV_DIR="$PROJECT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Erstelle Virtual Environment..."
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ Virtual Environment erstellt${NC}"
else
    echo -e "${YELLOW}ℹ️  Virtual Environment existiert bereits${NC}"
fi
echo ""

# Activate venv
echo "🔧 Aktiviere Virtual Environment..."
source "$VENV_DIR/bin/activate"
echo ""

# Upgrade pip
echo "⬆️  Upgrade pip..."
pip install --upgrade pip
echo ""

# Install requirements
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "📥 Installiere Python-Dependencies..."
    echo "   (Dies kann einige Minuten dauern...)"
    echo ""
    pip install -r "$REQUIREMENTS_FILE"
    echo ""
    echo -e "${GREEN}✅ Alle Dependencies installiert${NC}"
else
    echo -e "${RED}❌ requirements.txt nicht gefunden: $REQUIREMENTS_FILE${NC}"
    exit 1
fi

echo ""
echo "=================================================="
echo -e "${GREEN}✅ Python Setup abgeschlossen!${NC}"
echo "=================================================="
echo ""
echo "📊 Nützliche Befehle:"
echo "   Virtual Environment aktivieren: source venv/bin/activate"
echo "   AIfred starten: reflex run"
echo "   Tests ausführen: pytest"
echo ""
