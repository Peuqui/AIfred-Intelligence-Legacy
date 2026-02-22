#!/usr/bin/env bash
# Migration: llama-swap User-Service → geharteter System-Service
# Einmalig ausführen, dann löschen.
set -euo pipefail

echo "=== llama-swap Migration: User-Service → System-Service ==="
echo ""

# Prüfe ob als root/sudo ausgeführt
if [[ $EUID -ne 0 ]]; then
    echo "Bitte mit sudo ausführen: sudo bash $0"
    exit 1
fi

# 1. System-Service installieren
echo "[1/7] System-Service installieren..."
cp /tmp/llama-swap.service /etc/systemd/system/llama-swap.service
chmod 644 /etc/systemd/system/llama-swap.service
systemctl daemon-reload
echo "      OK"

# 2. sudoers für www-data
echo "[2/7] sudoers installieren..."
cp /tmp/ai-services-sudoers /etc/sudoers.d/ai-services
chmod 440 /etc/sudoers.d/ai-services
visudo -c -q
echo "      OK"

# 3. User-Service stoppen
echo "[3/7] User-Service stoppen..."
sudo -u mp XDG_RUNTIME_DIR=/run/user/$(id -u mp) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u mp)/bus \
    systemctl --user stop llama-swap 2>/dev/null || true
echo "      OK"

# 4. System-Service starten
echo "[4/7] System-Service starten..."
systemctl start llama-swap
systemctl enable llama-swap
echo "      OK"

# 5. User-Service disablen + löschen
echo "[5/7] User-Service aufräumen..."
sudo -u mp XDG_RUNTIME_DIR=/run/user/$(id -u mp) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u mp)/bus \
    systemctl --user disable llama-swap 2>/dev/null || true
rm -f /home/mp/.config/systemd/user/llama-swap.service
echo "      OK"

# 6. Wrapper löschen
echo "[6/7] Wrapper-Script löschen..."
rm -f /usr/local/bin/llama-swap-service-ctl
echo "      OK"

# 7. Verifizieren
echo "[7/7] Verifizierung..."
echo ""
STATUS=$(systemctl is-active llama-swap)
echo "  Service-Status: $STATUS"

if [[ "$STATUS" == "active" ]]; then
    sleep 2
    MODELS=$(curl -s --max-time 5 http://localhost:8100/v1/models 2>/dev/null | head -c 200)
    if [[ -n "$MODELS" ]]; then
        echo "  API erreichbar: OK"
    else
        echo "  API erreichbar: WARTET (autoscan läuft noch...)"
    fi
    echo ""
    echo "  Security-Score:"
    systemd-analyze security llama-swap.service 2>/dev/null | tail -1
    echo ""
    echo "=== Migration erfolgreich! ==="
else
    echo ""
    echo "=== FEHLER: Service nicht aktiv! ==="
    echo "  Prüfe mit: journalctl -u llama-swap -n 20"
    exit 1
fi
