#!/bin/bash
set -e

echo "============================================"
echo "  OpenClawBox WiFi Setup (AP+STA)"
echo "============================================"
echo ""

# Detect repo directory (script is in repo root)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$REPO_DIR/captive-portal/captive_portal.py" ]; then
    echo "ERROR: Cannot find captive-portal/captive_portal.py"
    echo "  Make sure you run this script from the repo directory:"
    echo "  sudo bash setup-openclawbox-wifi.sh"
    exit 1
fi

# Step 1: Install required packages
echo "[1/6] Installing required packages..."
apt-get update -qq
apt-get install -y network-manager dnsmasq hostapd iw wireless-tools python3

# Step 2: Detect WiFi interface
echo "[2/6] Detecting WiFi interface..."
WIFI_IFACE=$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | grep ':wifi$' | head -1 | cut -d: -f1)

if [ -z "$WIFI_IFACE" ]; then
    # Fallback: try iw
    WIFI_IFACE=$(iw dev 2>/dev/null | grep 'Interface' | head -1 | awk '{print $2}')
fi

if [ -z "$WIFI_IFACE" ]; then
    echo "ERROR: No WiFi interface found!"
    exit 1
fi

AP_IFACE="${WIFI_IFACE}ap"
echo "  WiFi interface: $WIFI_IFACE"
echo "  AP interface:   $AP_IFACE"

# Step 3: Configure NetworkManager
echo "[3/6] Configuring NetworkManager..."

# Configure netplan if available
if command -v netplan &>/dev/null; then
    tee /etc/netplan/01-network-manager-all.yaml > /dev/null <<'EOF'
network:
  version: 2
  renderer: NetworkManager
EOF
    chmod 600 /etc/netplan/01-network-manager-all.yaml
    find /etc/netplan/ -name '*.yaml' ! -name '01-network-manager-all.yaml' -delete 2>/dev/null || true
    netplan apply
fi

systemctl enable NetworkManager
systemctl start NetworkManager

# Disable dhcpcd if running (common on Raspberry Pi)
systemctl stop dhcpcd 2>/dev/null || true
systemctl disable dhcpcd 2>/dev/null || true

# Fix "Wait for Network to be Configured" boot delay (2min timeout)
if systemctl list-unit-files systemd-networkd-wait-online.service &>/dev/null; then
    systemctl disable systemd-networkd-wait-online.service 2>/dev/null || true
    systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true
    echo "  Disabled systemd-networkd-wait-online (boot delay fix)"
fi

# Disable hostapd system service (we manage it ourselves)
systemctl stop hostapd 2>/dev/null || true
systemctl disable hostapd 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

# Tell NetworkManager to ignore the virtual AP interface
cat > /etc/NetworkManager/conf.d/openclawbox-unmanaged.conf <<EOF
[keyfile]
unmanaged-devices=interface-name:${AP_IFACE}
EOF

# Reduce WiFi auth retries for faster failure detection
cat > /etc/NetworkManager/conf.d/openclawbox-timeout.conf <<'EOF'
[connection]
auth-retries=1
connection.wait-device-timeout=0
EOF

nmcli general reload
echo "  NetworkManager configured"

# Step 4: Install captive portal and UI
echo "[4/6] Installing captive portal..."

cp "$REPO_DIR/captive-portal/captive_portal.py" /usr/local/bin/openclawbox-captive-portal.py
chmod +x /usr/local/bin/openclawbox-captive-portal.py

mkdir -p /usr/local/share/openclawbox-wifi/ui
mkdir -p /var/lib/openclawbox
cp "$REPO_DIR/ui-custom/index.html" /usr/local/share/openclawbox-wifi/ui/

cp "$REPO_DIR/wifi-switch/server.py" /usr/local/bin/openclawbox-wifi-switch.py
chmod +x /usr/local/bin/openclawbox-wifi-switch.py

echo "  Files installed"

# Step 5: Create systemd services
echo "[5/6] Creating systemd services..."

# Stop old services if running
systemctl stop openclawbox-wifi.service 2>/dev/null || true
systemctl stop openclawbox-wifi-switch.service 2>/dev/null || true

# Main captive portal service
cat > /etc/systemd/system/openclawbox-wifi.service <<EOF
[Unit]
Description=OpenClawBox WiFi Captive Portal (AP+STA)
After=NetworkManager.service dbus.service network-online.target
Wants=NetworkManager.service network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/openclawbox-captive-portal.py
ExecStopPost=/bin/bash -c 'iw dev ${AP_IFACE} del 2>/dev/null; killall hostapd 2>/dev/null; iptables -t nat -F PREROUTING 2>/dev/null; true'
Restart=always
RestartSec=10
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
EOF

# WiFi switch service (change WiFi from browser)
cat > /etc/systemd/system/openclawbox-wifi-switch.service <<'EOF'
[Unit]
Description=OpenClawBox WiFi Switch
After=NetworkManager.service network-online.target
Wants=NetworkManager.service network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/bin/openclawbox-wifi-switch.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Step 6: Enable and start services
echo "[6/6] Starting services..."
systemctl enable openclawbox-wifi.service
systemctl enable openclawbox-wifi-switch.service
systemctl start openclawbox-wifi.service
systemctl start openclawbox-wifi-switch.service

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  WiFi interface: $WIFI_IFACE"
echo "  AP interface:   $AP_IFACE"
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
