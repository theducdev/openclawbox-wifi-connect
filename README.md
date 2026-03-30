# OpenClawBox WiFi Connect

Giao diện cài đặt WiFi tuỳ chỉnh cho thiết bị OpenClawBox, dựa trên [balena-os/wifi-connect](https://github.com/balena-os/wifi-connect).

Khi thiết bị chưa kết nối WiFi, nó sẽ phát một mạng Access Point với captive portal cho phép người dùng chọn mạng WiFi và nhập mật khẩu từ điện thoại hoặc laptop.

## Cách hoạt động

1. Thiết bị tạo Access Point (mặc định SSID: `WiFi Connect`)
2. Người dùng kết nối điện thoại/laptop vào Access Point
3. Captive portal hiển thị giao diện cài đặt WiFi (tiếng Việt)
4. Người dùng chọn mạng WiFi và nhập mật khẩu
5. Thiết bị kết nối vào mạng WiFi đã chọn, cấu hình được **lưu vĩnh viễn** bởi NetworkManager

> **WiFi được lưu tự động**: Sau khi kết nối thành công, NetworkManager lưu cấu hình WiFi vào `/etc/NetworkManager/system-connections/`. Khi tắt máy bật lại, thiết bị sẽ **tự động kết nối lại** mà không cần cài đặt lại.

## Cài đặt trên Ubuntu (Mini PC - Không dùng Docker)

### Yêu cầu

- Ubuntu 20.04 / 22.04 / 24.04 (x86_64 hoặc aarch64)
- Có card WiFi
- Quyền root

### Bước 1: Cài đặt các gói cần thiết

```bash
sudo apt-get update
sudo apt-get install -y network-manager dnsmasq wireless-tools curl
```

### Bước 2: Kích hoạt NetworkManager, tắt netplan/dhcpcd

Ubuntu mặc định dùng netplan. Cần chuyển sang NetworkManager để wifi-connect hoạt động.

```bash
# Tạo file cấu hình netplan dùng NetworkManager
sudo tee /etc/netplan/01-network-manager-all.yaml > /dev/null <<'EOF'
network:
  version: 2
  renderer: NetworkManager
EOF

# Xoá các file netplan cũ nếu có (giữ lại file vừa tạo)
sudo find /etc/netplan/ -name '*.yaml' ! -name '01-network-manager-all.yaml' -delete

# Áp dụng netplan
sudo netplan apply

# Bật NetworkManager
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager

# Tắt dhcpcd nếu đang chạy (thường có trên Raspberry Pi OS)
sudo systemctl stop dhcpcd 2>/dev/null
sudo systemctl disable dhcpcd 2>/dev/null
```

Kiểm tra NetworkManager đã hoạt động:

```bash
nmcli general status
# Kết quả mong đợi: STATE = connected (hoặc disconnected nếu chưa có WiFi)
```

### Bước 3: Tải wifi-connect binary

```bash
# Tự động detect kiến trúc
ARCH=$(uname -m)
case $ARCH in
    "x86_64")  BINARY_ARCH="x86_64-unknown-linux-gnu" ;;
    "aarch64") BINARY_ARCH="aarch64-unknown-linux-gnu" ;;
    "armv7l")  BINARY_ARCH="armv7-unknown-linux-gnueabihf" ;;
    *)         echo "Kiến trúc không hỗ trợ: $ARCH"; exit 1 ;;
esac

# Tải và giải nén
curl -Ls "https://github.com/balena-os/wifi-connect/releases/latest/download/wifi-connect-${BINARY_ARCH}.tar.gz" \
  | sudo tar -xz -C /usr/local/sbin/

# Kiểm tra
wifi-connect --version
```

### Bước 4: Cài đặt giao diện OpenClawBox

```bash
# Clone repo
git clone https://github.com/theducdev/openclawbox-wifi-connect.git /tmp/openclawbox-wifi-connect

# Copy giao diện vào đúng thư mục
sudo mkdir -p /usr/local/share/wifi-connect/ui
sudo cp /tmp/openclawbox-wifi-connect/ui-custom/index.html /usr/local/share/wifi-connect/ui/

# Dọn dẹp
rm -rf /tmp/openclawbox-wifi-connect
```

### Bước 5: Tạo script khởi động

```bash
sudo tee /usr/local/bin/openclawbox-wifi.sh > /dev/null <<'SCRIPT'
#!/bin/bash

# Chờ NetworkManager sẵn sàng
sleep 5

# Kiểm tra đã có kết nối WiFi chưa
if iwgetid -r > /dev/null 2>&1; then
    echo "WiFi đã kết nối: $(iwgetid -r). Bỏ qua WiFi Connect."
    exit 0
fi

echo "Chưa có WiFi. Khởi động WiFi Connect..."
wifi-connect \
    --portal-ssid "OpenClawBox Setup" \
    --portal-gateway 192.168.42.1 \
    --portal-listening-port 80 \
    --ui-directory /usr/local/share/wifi-connect/ui
SCRIPT

sudo chmod +x /usr/local/bin/openclawbox-wifi.sh
```

### Bước 6: Tạo systemd service (tự chạy khi khởi động)

```bash
sudo tee /etc/systemd/system/openclawbox-wifi.service > /dev/null <<'EOF'
[Unit]
Description=OpenClawBox WiFi Connect
After=NetworkManager.service dbus.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/openclawbox-wifi.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable openclawbox-wifi.service
sudo systemctl start openclawbox-wifi.service
```

### Bước 7: Kiểm tra

```bash
# Xem trạng thái service
sudo systemctl status openclawbox-wifi.service

# Xem log
sudo journalctl -u openclawbox-wifi.service -f
```

### Test thử

1. **Nếu chưa có WiFi**: Service sẽ tự phát mạng `OpenClawBox Setup`. Dùng điện thoại kết nối vào mạng này, captive portal sẽ hiện ra để chọn WiFi.
2. **Sau khi cài WiFi thành công**: Tắt máy bật lại, thiết bị sẽ tự kết nối WiFi đã lưu.
3. **Nếu WiFi đã lưu không khả dụng** (đổi mật khẩu, mất sóng...): Service sẽ tự phát lại Access Point để cài đặt lại.

### Xác nhận WiFi đã được lưu

```bash
# Liệt kê các kết nối WiFi đã lưu
nmcli connection show

# Xem chi tiết một kết nối
nmcli connection show "Tên_WiFi"

# File cấu hình được lưu tại
ls /etc/NetworkManager/system-connections/
```

## Tuỳ chỉnh

### Biến môi trường / Tham số

| Tham số | Biến môi trường | Mặc định | Mô tả |
|---------|-----------------|----------|--------|
| `--portal-ssid` | `PORTAL_SSID` | `WiFi Connect` | Tên mạng Access Point |
| `--portal-passphrase` | `PORTAL_PASSPHRASE` | _(không có)_ | Mật khẩu AP (tuỳ chọn) |
| `--portal-gateway` | `PORTAL_GATEWAY` | `192.168.42.1` | Gateway captive portal |
| `--portal-listening-port` | `PORTAL_LISTENING_PORT` | `80` | Port web server |
| `--ui-directory` | `UI_DIRECTORY` | `ui` | Thư mục giao diện |
| `--portal-interface` | `PORTAL_INTERFACE` | _(tự detect)_ | Interface WiFi |
| `--activity-timeout` | `ACTIVITY_TIMEOUT` | `0` | Tự tắt sau N giây không hoạt động |

### Đổi tên Access Point

Sửa trong `/usr/local/bin/openclawbox-wifi.sh`:

```bash
--portal-ssid "Tên tuỳ chỉnh"
```

### Đặt mật khẩu cho Access Point

```bash
--portal-passphrase "matkhau123"
```

## Cài đặt trên balenaOS (Docker)

### docker-compose.yml

```yaml
version: "2.1"

services:
    wifi-connect:
        build: ./
        network_mode: "host"
        labels:
            io.balena.features.dbus: '1'
        cap_add:
            - NET_ADMIN
        environment:
            DBUS_SYSTEM_BUS_ADDRESS: "unix:path=/host/run/dbus/system_bus_socket"
```

## Phát triển

Chạy mock server để test giao diện locally:

```bash
node mock-server.js
```

Mở trình duyệt tại `http://localhost:3000`

## Gỡ lỗi

```bash
# Kiểm tra NetworkManager
sudo systemctl status NetworkManager

# Kiểm tra service
sudo systemctl status openclawbox-wifi.service
sudo journalctl -u openclawbox-wifi.service --no-pager -n 50

# Kiểm tra interface WiFi
nmcli device wifi list

# Xoá kết nối WiFi đã lưu (nếu cần cài lại)
nmcli connection delete "Tên_WiFi"

# Khởi động lại service (bật lại Access Point)
sudo systemctl restart openclawbox-wifi.service
```

## Liên hệ

- Zalo: [0868287651](https://zalo.me/0868287651)
- Website: [openclaw-box.com](https://openclaw-box.com)
- Tài liệu: [docs.openclaw-box.com](https://docs.openclaw-box.com)

## License

Dựa trên [wifi-connect](https://github.com/balena-os/wifi-connect) của balena.io, phân phối theo [Apache License 2.0](./LICENSE).
