#!/usr/bin/env python3
"""OpenClawBox WiFi Captive Portal with AP+STA concurrent mode.

Creates a virtual AP interface while using the main interface for STA connection.
The AP stays up during connection attempts, so the phone never loses connectivity.
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
STA_IFACE = None  # Auto-detected
AP_IFACE = None   # Auto-generated from STA_IFACE
AP_IP = "192.168.42.1"
AP_NETMASK = "255.255.255.0"
DHCP_START = "192.168.42.10"
DHCP_END = "192.168.42.50"
PORTAL_PORT = 8080
SSID = "OpenClawBox Setup"
CHANNEL = 1
UI_DIR = "/usr/local/share/openclawbox-wifi/ui"
AP_TEARDOWN_DELAY = 30

hostapd_proc = None
dnsmasq_proc = None


def run(cmd, **kwargs):
    """Run a command and return the result."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


WATCHDOG_INTERVAL = 15  # seconds between WiFi checks
WATCHDOG_FAIL_THRESHOLD = 4  # consecutive failures before restarting AP
REBOOT_COUNT_FILE = "/var/lib/openclawbox/reboot-count"
MAX_REBOOTS = 5


def get_reboot_count():
    """Get current reboot attempt count."""
    try:
        with open(REBOOT_COUNT_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def set_reboot_count(count):
    """Save reboot attempt count."""
    os.makedirs(os.path.dirname(REBOOT_COUNT_FILE), exist_ok=True)
    with open(REBOOT_COUNT_FILE, "w") as f:
        f.write(str(count))


def clear_reboot_count():
    """Reset reboot count after successful WiFi detection."""
    try:
        os.remove(REBOOT_COUNT_FILE)
    except FileNotFoundError:
        pass


def reboot_if_no_wifi():
    """Reboot machine if WiFi card not found, up to MAX_REBOOTS times."""
    count = get_reboot_count()
    if count >= MAX_REBOOTS:
        print(f"  Already rebooted {count} times. Giving up — WiFi card may be dead.")
        return False
    count += 1
    set_reboot_count(count)
    print(f"  WiFi not found. Rebooting... (attempt {count}/{MAX_REBOOTS})")
    time.sleep(2)
    subprocess.run(["reboot"])
    time.sleep(30)  # Wait for reboot to take effect
    return True


def detect_wifi_interface():
    """Auto-detect the WiFi interface name, with retries at boot."""
    global STA_IFACE, AP_IFACE
    for attempt in range(10):
        result = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
        for line in result.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wifi":
                STA_IFACE = parts[0]
                AP_IFACE = STA_IFACE + "ap"
                print(f"  WiFi interface detected: {STA_IFACE}")
                clear_reboot_count()
                return
        # Fallback: try iw
        result = run(["iw", "dev"])
        match = re.search(r"Interface\s+(\S+)", result.stdout)
        if match:
            STA_IFACE = match.group(1)
            AP_IFACE = STA_IFACE + "ap"
            print(f"  WiFi interface detected: {STA_IFACE}")
            clear_reboot_count()
            return
        if attempt < 9:
            print(f"  WiFi device not found, retrying ({attempt + 1}/10)...")
            time.sleep(2)

    # WiFi not found after all retries — try rebooting
    if reboot_if_no_wifi():
        sys.exit(0)  # Will reboot, exit cleanly
    raise RuntimeError(f"No WiFi interface found after 10 retries and {MAX_REBOOTS} reboots")


def get_current_ssid():
    """Get the currently connected WiFi SSID on STA interface."""
    try:
        result = run(["iwgetid", "-r", STA_IFACE])
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def is_wifi_connected():
    """Check if STA interface is connected to WiFi."""
    return bool(get_current_ssid())


def get_mac(iface):
    """Get MAC address of an interface."""
    result = run(["ip", "link", "show", iface])
    match = re.search(r"link/ether\s+([0-9a-f:]+)", result.stdout)
    return match.group(1) if match else None


def increment_mac(mac):
    """Increment last byte of MAC address for virtual interface."""
    parts = mac.split(":")
    parts[-1] = format((int(parts[-1], 16) + 1) % 256, "02x")
    # Set locally administered bit
    parts[0] = format(int(parts[0], 16) | 0x02, "02x")
    return ":".join(parts)


def get_phy_name():
    """Get the physical WiFi device name (phyX)."""
    result = run(["iw", "dev", STA_IFACE, "info"])
    match = re.search(r"wiphy\s+(\d+)", result.stdout)
    if match:
        return f"phy{match.group(1)}"
    return None


def setup_ap_interface():
    """Create virtual AP interface."""
    print(f"[1/5] Creating AP interface {AP_IFACE}...")

    # Get phy name
    phy = get_phy_name()
    if not phy:
        raise RuntimeError(f"Cannot find phy for {STA_IFACE}")

    # Delete if exists
    run(["iw", "dev", AP_IFACE, "del"], check=False)
    time.sleep(0.5)

    # Create virtual AP interface
    result = run(["iw", phy, "interface", "add", AP_IFACE, "type", "__ap"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create AP interface: {result.stderr}")

    # Set different MAC address
    base_mac = get_mac(STA_IFACE)
    if not base_mac:
        raise RuntimeError(f"Cannot get MAC of {STA_IFACE}")
    ap_mac = increment_mac(base_mac)
    run(["ip", "link", "set", AP_IFACE, "address", ap_mac])
    run(["ip", "link", "set", AP_IFACE, "up"])

    print(f"  AP interface {AP_IFACE} created (MAC: {ap_mac})")


def start_hostapd():
    """Start hostapd on the AP interface."""
    global hostapd_proc
    print(f"[2/5] Starting hostapd (SSID: {SSID})...")

    conf = f"""interface={AP_IFACE}
driver=nl80211
ssid={SSID}
hw_mode=g
channel={CHANNEL}
wmm_enabled=0
auth_algs=1
wpa=0
ignore_broadcast_ssid=0
"""
    conf_path = "/tmp/openclawbox-hostapd.conf"
    with open(conf_path, "w") as f:
        f.write(conf)

    # Kill existing
    run(["killall", "hostapd"], check=False)
    time.sleep(0.5)

    hostapd_proc = subprocess.Popen(
        ["hostapd", conf_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)
    if hostapd_proc.poll() is not None:
        out = hostapd_proc.stdout.read().decode() if hostapd_proc.stdout else ""
        raise RuntimeError(f"hostapd failed to start: {out}")

    print("  hostapd started")


def configure_ap_network():
    """Set IP address on AP interface."""
    print(f"[3/5] Configuring AP network ({AP_IP})...")
    run(["ip", "addr", "flush", "dev", AP_IFACE], check=False)
    run(["ip", "addr", "add", f"{AP_IP}/24", "dev", AP_IFACE])
    run(["ip", "link", "set", AP_IFACE, "up"])
    print(f"  AP network configured")


def start_dnsmasq():
    """Start dnsmasq for DHCP and DNS on AP interface."""
    global dnsmasq_proc
    print(f"[4/5] Starting dnsmasq...")

    conf = f"""interface={AP_IFACE}
bind-interfaces
dhcp-range={DHCP_START},{DHCP_END},{AP_NETMASK},24h
dhcp-option=3,{AP_IP}
dhcp-option=6,{AP_IP}
address=/#/{AP_IP}
no-resolv
log-dhcp
"""
    conf_path = "/tmp/openclawbox-dnsmasq.conf"
    with open(conf_path, "w") as f:
        f.write(conf)

    # Kill existing dnsmasq instances on AP interface
    run(["killall", "-9", "dnsmasq"], check=False)
    time.sleep(0.5)

    dnsmasq_proc = subprocess.Popen(
        ["dnsmasq", "--no-daemon", f"--conf-file={conf_path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(1)
    if dnsmasq_proc.poll() is not None:
        out = dnsmasq_proc.stdout.read().decode() if dnsmasq_proc.stdout else ""
        raise RuntimeError(f"dnsmasq failed to start: {out}")

    print("  dnsmasq started")


def setup_iptables():
    """Redirect HTTP traffic to captive portal."""
    # Clean up first
    cleanup_iptables()
    # Redirect port 80 -> portal port
    run([
        "iptables", "-t", "nat", "-A", "PREROUTING",
        "-i", AP_IFACE, "-p", "tcp", "--dport", "80",
        "-j", "DNAT", "--to-destination", f"{AP_IP}:{PORTAL_PORT}",
    ])


def cleanup_iptables():
    """Remove iptables rules."""
    run([
        "iptables", "-t", "nat", "-D", "PREROUTING",
        "-i", AP_IFACE, "-p", "tcp", "--dport", "80",
        "-j", "DNAT", "--to-destination", f"{AP_IP}:{PORTAL_PORT}",
    ], check=False)


def scan_networks():
    """Scan for WiFi networks using nmcli on STA interface."""
    run(["nmcli", "device", "wifi", "rescan", "ifname", STA_IFACE],
        check=False, timeout=10)
    time.sleep(2)
    result = run(
        ["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "device", "wifi", "list",
         "ifname", STA_IFACE],
        timeout=15,
    )
    networks = []
    seen = set()
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        # nmcli -t uses : as separator, but SSID might contain :
        # Format: SSID:SECURITY:SIGNAL
        # Parse from the right since SIGNAL is always a number
        parts = line.rsplit(":", 2)
        if len(parts) < 3:
            continue
        ssid = parts[0].strip().replace("\\:", ":")
        security_raw = parts[1].strip()
        signal = parts[2].strip()
        if not ssid or ssid in seen or ssid == SSID:
            continue
        seen.add(ssid)
        if "802.1X" in security_raw or "EAP" in security_raw:
            security = "enterprise"
        elif "WPA" in security_raw:
            security = "wpa"
        elif "WEP" in security_raw:
            security = "wep"
        else:
            security = "open"
        networks.append({
            "ssid": ssid,
            "security": security,
        })
    return networks


def try_connect(ssid, passphrase, identity=""):
    """Try to connect to a WiFi network. Returns (success, message)."""
    # Delete existing connection to avoid conflicts
    run(["nmcli", "connection", "delete", ssid], check=False, capture_output=True)

    cmd = ["nmcli", "--wait", "15", "device", "wifi", "connect", ssid,
           "ifname", STA_IFACE]
    if passphrase:
        cmd += ["password", passphrase]

    try:
        result = run(cmd, timeout=30)
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            run(["nmcli", "connection", "delete", ssid], check=False)
            return False, translate_error(error)

        # nmcli may return 0 before authentication completes
        # Wait and verify actual connection
        for i in range(10):
            time.sleep(1)
            # Check if interface is actually connected
            state = run(["nmcli", "-t", "-f", "STATE", "device", "show", STA_IFACE])
            if "connected" in state.stdout and "disconnected" not in state.stdout:
                # Double-check with iwgetid
                ssid_check = get_current_ssid()
                if ssid_check:
                    return True, f"Đã kết nối thành công đến {ssid}"
            # Check if connection failed
            if "disconnected" in state.stdout and i >= 3:
                run(["nmcli", "connection", "delete", ssid], check=False)
                return False, "Mật khẩu WiFi không đúng. Vui lòng kiểm tra và thử lại."

        # Timeout waiting for verification
        actual_ssid = get_current_ssid()
        if actual_ssid:
            return True, f"Đã kết nối thành công đến {actual_ssid}"
        run(["nmcli", "connection", "delete", ssid], check=False)
        return False, "Mật khẩu WiFi không đúng. Vui lòng kiểm tra và thử lại."

    except subprocess.TimeoutExpired:
        run(["nmcli", "connection", "delete", ssid], check=False)
        return False, "Kết nối quá thời gian chờ. Vui lòng thử lại."


def translate_error(error):
    """Translate nmcli errors to Vietnamese."""
    error_lower = error.lower()
    if "secrets were required" in error_lower or "no secrets" in error_lower:
        return "Mật khẩu WiFi không đúng. Vui lòng kiểm tra và thử lại."
    if "no network" in error_lower or "not found" in error_lower:
        return "Không tìm thấy mạng WiFi. Vui lòng thử lại."
    if "timeout" in error_lower:
        return "Kết nối quá thời gian chờ. Vui lòng thử lại."
    return f"Kết nối thất bại: {error}"


def get_sta_ip():
    """Get IP address of STA interface."""
    result = run(["ip", "-4", "addr", "show", STA_IFACE])
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result.stdout)
    return match.group(1) if match else ""


def teardown():
    """Clean up everything."""
    global hostapd_proc, dnsmasq_proc
    print("Shutting down...")
    cleanup_iptables()
    if hostapd_proc:
        hostapd_proc.terminate()
        hostapd_proc = None
    if dnsmasq_proc:
        dnsmasq_proc.terminate()
        dnsmasq_proc = None
    run(["ip", "link", "set", AP_IFACE, "down"], check=False)
    run(["iw", "dev", AP_IFACE, "del"], check=False)
    print("Cleanup complete")


class PortalHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the captive portal."""

    def do_GET(self):
        if self.path == "/networks":
            self.handle_networks()
        elif self.path == "/" or self.path == "/index.html":
            self.serve_file("index.html", "text/html")
        elif self.path in ("/hotspot-detect.html", "/generate_204",
                           "/gen_204", "/ncsi.txt", "/check_network_status.txt",
                           "/connectivity-check.html"):
            # Captive portal detection - redirect to portal
            self.send_response(302)
            self.send_header("Location", f"http://{AP_IP}:{PORTAL_PORT}/")
            self.end_headers()
        else:
            # Unknown path - redirect to portal (for captive portal detection)
            self.send_response(302)
            self.send_header("Location", f"http://{AP_IP}:{PORTAL_PORT}/")
            self.end_headers()

    def do_POST(self):
        if self.path == "/connect":
            self.handle_connect()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def handle_networks(self):
        try:
            networks = scan_networks()
            self.send_json(200, networks)
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def handle_connect(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except Exception:
            self.send_json(400, {"status": "error", "message": "Invalid request"})
            return

        ssid = body.get("ssid", "")
        passphrase = body.get("passphrase", "")
        identity = body.get("identity", "")

        if not ssid:
            self.send_json(400, {"status": "error", "message": "Vui lòng chọn mạng WiFi"})
            return

        print(f"Attempting to connect to '{ssid}'...")

        success, message = try_connect(ssid, passphrase, identity)

        if success:
            ip = get_sta_ip()
            print(f"Connected to '{ssid}' (IP: {ip})")
            self.send_json(200, {
                "status": "success",
                "message": message,
                "ssid": ssid,
                "ip": ip,
            })
        else:
            print(f"Failed to connect to '{ssid}': {message}")
            self.send_json(200, {
                "status": "error",
                "message": message,
            })

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, filename, content_type):
        filepath = os.path.join(UI_DIR, filename)
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "File not found")

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}" if args else "")


portal_server = None
portal_thread = None


def start_portal():
    """Start the AP and captive portal HTTP server."""
    global portal_server, portal_thread

    # Ensure STA is disconnected so AP can scan
    run(["nmcli", "device", "disconnect", STA_IFACE], check=False)

    # Setup AP
    setup_ap_interface()
    start_hostapd()
    configure_ap_network()
    start_dnsmasq()
    setup_iptables()

    # Start HTTP server in a thread
    print(f"[5/5] Starting portal on http://{AP_IP}:{PORTAL_PORT}")
    print(f"  AP SSID: {SSID}")
    print(f"  Portal:  http://{AP_IP}:{PORTAL_PORT}")

    portal_server = HTTPServer((AP_IP, PORTAL_PORT), PortalHandler)
    portal_thread = threading.Thread(target=portal_server.serve_forever, daemon=True)
    portal_thread.start()


def stop_portal():
    """Stop the AP and captive portal HTTP server."""
    global portal_server, portal_thread
    if portal_server:
        portal_server.shutdown()
        portal_server = None
        portal_thread = None
    teardown()


def watchdog_loop():
    """Monitor WiFi and restart AP if connection drops."""
    fail_count = 0

    while True:
        time.sleep(WATCHDOG_INTERVAL)

        if is_wifi_connected():
            if fail_count > 0:
                print(f"[watchdog] WiFi reconnected: {get_current_ssid()}")
            fail_count = 0
        else:
            fail_count += 1
            print(f"[watchdog] WiFi disconnected ({fail_count}/{WATCHDOG_FAIL_THRESHOLD})")

            if fail_count >= WATCHDOG_FAIL_THRESHOLD:
                print("[watchdog] WiFi lost — restarting captive portal AP...")
                fail_count = 0
                return  # Exit watchdog to restart portal


def main():
    print("=" * 44)
    print("  OpenClawBox WiFi Captive Portal (AP+STA)")
    print("=" * 44)

    # Auto-detect WiFi interface
    detect_wifi_interface()

    while True:
        ssid = get_current_ssid()
        if ssid:
            print(f"WiFi connected: {ssid}. Monitoring...")
            watchdog_loop()
            # watchdog_loop returns when WiFi is lost
            continue

        # WiFi not connected — start captive portal
        print("WiFi not connected. Starting captive portal...")
        start_portal()

        # Wait until WiFi connects
        while not is_wifi_connected():
            time.sleep(5)

        # Connected! Stop portal after delay
        ssid = get_current_ssid()
        print(f"WiFi connected to '{ssid}'. Stopping portal in {AP_TEARDOWN_DELAY}s...")
        time.sleep(AP_TEARDOWN_DELAY)
        stop_portal()
        print("Portal stopped. Entering watchdog mode.")


def signal_handler(sig, frame):
    teardown()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        teardown()
        sys.exit(1)
