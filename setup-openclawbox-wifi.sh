#!/bin/bash
set -e

echo "============================================"
echo "  OpenClawBox WiFi Setup (AP+STA)"
echo "============================================"
echo ""

# Step 1: Install required packages
echo "[1/5] Installing required packages..."
apt-get update -qq
apt-get install -y network-manager dnsmasq hostapd iw wireless-tools python3

# Step 2: Configure NetworkManager
echo "[2/5] Configuring NetworkManager..."
tee /etc/netplan/01-network-manager-all.yaml > /dev/null <<'EOF'
network:
  version: 2
  renderer: NetworkManager
EOF
chmod 600 /etc/netplan/01-network-manager-all.yaml

find /etc/netplan/ -name '*.yaml' ! -name '01-network-manager-all.yaml' -delete 2>/dev/null || true

netplan apply
systemctl enable NetworkManager
systemctl start NetworkManager

# Disable dhcpcd if running (common on Raspberry Pi)
systemctl stop dhcpcd 2>/dev/null || true
systemctl disable dhcpcd 2>/dev/null || true

# Disable hostapd system service (we manage it ourselves)
systemctl stop hostapd 2>/dev/null || true
systemctl disable hostapd 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

# Tell NetworkManager to ignore the virtual AP interface
tee /etc/NetworkManager/conf.d/openclawbox-unmanaged.conf > /dev/null <<'EOF'
[keyfile]
unmanaged-devices=interface-name:wlp3s0ap
EOF

# Reduce WiFi auth retries for faster failure detection
tee /etc/NetworkManager/conf.d/openclawbox-timeout.conf > /dev/null <<'EOF'
[connection]
auth-retries=1
EOF

nmcli general reload

echo "  NetworkManager status:"
nmcli general status || true

# Step 3: Install captive portal and UI
echo "[3/5] Installing captive portal..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${SCRIPT_DIR}/openclawbox-wifi-connect"

if [ ! -d "$REPO_DIR" ]; then
    REPO_DIR="/home/techla/openclawbox-wifi-connect"
fi

cp "$REPO_DIR/captive-portal/captive_portal.py" /usr/local/bin/openclawbox-captive-portal.py
chmod +x /usr/local/bin/openclawbox-captive-portal.py

mkdir -p /usr/local/share/openclawbox-wifi/ui
cp "$REPO_DIR/ui-custom/index.html" /usr/local/share/openclawbox-wifi/ui/

cp "$REPO_DIR/wifi-switch/server.py" /usr/local/bin/openclawbox-wifi-switch.py
chmod +x /usr/local/bin/openclawbox-wifi-switch.py

echo "  Captive portal installed"

# Step 4: Create systemd services
echo "[4/5] Creating systemd services..."

# Main captive portal service
tee /etc/systemd/system/openclawbox-wifi.service > /dev/null <<'EOF'
[Unit]
Description=OpenClawBox WiFi Captive Portal (AP+STA)
After=NetworkManager.service dbus.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/openclawbox-captive-portal.py
ExecStopPost=/bin/bash -c 'iw dev wlp3s0ap del 2>/dev/null; killall hostapd 2>/dev/null; iptables -t nat -F PREROUTING 2>/dev/null; true'
Restart=on-failure
RestartSec=10
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
EOF

# WiFi switch service (change WiFi from browser)
tee /etc/systemd/system/openclawbox-wifi-switch.service > /dev/null <<'EOF'
[Unit]
Description=OpenClawBox WiFi Switch
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/openclawbox-wifi-switch.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Step 5: Enable and start services
echo "[5/5] Starting services..."
systemctl enable openclawbox-wifi.service
systemctl enable openclawbox-wifi-switch.service
systemctl start openclawbox-wifi.service
systemctl start openclawbox-wifi-switch.service

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  Service status:"
systemctl status openclawbox-wifi.service --no-pager || true
echo ""
echo "  If WiFi is not connected, the device will"
echo "  broadcast AP: 'OpenClawBox Setup'"
echo "  Connect to it and the captive portal will"
echo "  open automatically to configure WiFi."
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status openclawbox-wifi.service"
echo "    sudo journalctl -u openclawbox-wifi.service -f"
echo "    sudo systemctl restart openclawbox-wifi.service"
echo ""
