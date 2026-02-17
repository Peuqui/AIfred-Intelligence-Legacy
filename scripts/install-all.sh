#!/bin/bash
#
# AIfred Intelligence - Complete Installation Script
# Installiert alles: Python-Environment, Systemd-Services (optional)
#

set -e  # Exit on error

echo "=================================================="
echo "  AIfred Intelligence - Vollständige Installation"
echo "=================================================="
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "📂 Projekt-Verzeichnis: $PROJECT_DIR"
echo ""

# ============================================================
# SCHRITT 1: Python Environment Setup (OHNE sudo)
# ============================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Schritt 1/2: Python Environment Setup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ -f "$SCRIPT_DIR/setup-python.sh" ]; then
    bash "$SCRIPT_DIR/setup-python.sh"
else
    echo -e "${RED}❌ Script nicht gefunden: $SCRIPT_DIR/setup-python.sh${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Python Environment bereit${NC}"
echo ""
sleep 1

# ============================================================
# SCHRITT 2: Systemd Services Installation (Optional, MIT sudo)
# ============================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Schritt 2/2: Systemd Services Installation (Optional)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Systemd-Services für automatischen Start beim Booten."
echo -e "${YELLOW}⚠️  Benötigt sudo-Rechte!${NC}"
echo ""
read -p "Systemd-Services installieren? (j/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[JjYy]$ ]]; then
    if [ -f "$SCRIPT_DIR/install-services.sh" ]; then
        echo "   Starte Installation mit sudo..."
        sudo bash "$SCRIPT_DIR/install-services.sh"
    else
        echo -e "${RED}❌ Script nicht gefunden: $SCRIPT_DIR/install-services.sh${NC}"
        echo "   Überspringe Systemd-Installation..."
    fi
else
    echo -e "${YELLOW}⏭️  Systemd-Installation übersprungen${NC}"
    echo ""
    echo "   Du kannst AIfred manuell starten mit:"
    echo "   cd $PROJECT_DIR"
    echo "   source venv/bin/activate"
    echo "   reflex run"
fi

echo ""
echo "=================================================="
echo -e "${GREEN}✅ Installation abgeschlossen!${NC}"
echo "=================================================="
echo ""
echo "📊 Nächste Schritte:"
echo ""
echo "1. ChromaDB starten (falls installiert):"
echo "   cd $PROJECT_DIR/docker"
echo "   docker compose up -d chromadb"
echo ""
echo "2. AIfred starten:"
echo "   cd $PROJECT_DIR"
echo "   source venv/bin/activate"
echo "   reflex run"
echo ""
echo "3. Im Browser öffnen:"
echo "   http://localhost:3002"
echo ""
echo "📚 Dokumentation: $PROJECT_DIR/README.md"
echo ""
