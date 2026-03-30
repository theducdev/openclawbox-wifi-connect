# OpenClawBox WiFi Connect

Captive portal cài đặt WiFi cho thiết bị OpenClawBox, sử dụng chế độ **AP+STA đồng thời** trên Linux.

Khi thiết bị chưa kết nối WiFi, nó sẽ phát Access Point với captive portal cho phép người dùng chọn mạng WiFi và nhập mật khẩu từ điện thoại.

## Cách hoạt động

1. Thiết bị tạo Access Point (SSID: `OpenClawBox Setup`)
2. Người dùng kết nối điện thoại vào Access Point
3. Captive portal hiển thị giao diện cài đặt WiFi (tiếng Việt)
4. Người dùng chọn mạng WiFi và nhập mật khẩu
5. Thiết bị kết nối WiFi **trong khi AP vẫn chạy** — kết quả thành công/thất bại hiển thị ngay trên điện thoại
6. Cấu hình WiFi được **lưu vĩnh viễn** bởi NetworkManager

### AP+STA: Giải quyết vấn đề gì?

Các giải pháp cũ (balena wifi-connect, comitup...) phải **tắt AP để thử kết nối WiFi**, khiến điện thoại mất kết nối với portal và không nhận được kết quả. OpenClawBox sử dụng **virtual interface** để chạy AP và STA đồng thời trên cùng chip WiFi — điện thoại luôn giữ kết nối với portal.

## Cài đặt nhanh

### Yêu cầu

- Ubuntu 20.04 / 22.04 / 24.04
- Card WiFi hỗ trợ AP+STA đồng thời (kiểm tra: `iw list | grep -A 8 "valid interface"`)
- Quyền root

### Cài đặt

```bash
git clone https://github.com/theducdev/openclawbox-wifi-connect.git
cd openclawbox-wifi-connect
sudo bash setup-openclawbox-wifi.sh
```

Script sẽ tự động:
- Cài các gói cần thiết (`network-manager`, `hostapd`, `iw`, `dnsmasq`)
- Cấu hình NetworkManager
- Cài captive portal và WiFi switch service
- Tạo và bật systemd services

### Kiểm tra

```bash
# Trạng thái service
sudo systemctl status openclawbox-wifi.service

# Xem log
sudo journalctl -u openclawbox-wifi.service -f
```

## Sử dụng

### Lần đầu (chưa có WiFi)

1. Thiết bị tự phát mạng **"OpenClawBox Setup"**
2. Kết nối điện thoại vào mạng này
3. Captive portal tự mở (hoặc mở `192.168.42.1:8080`)
4. Chọn WiFi, nhập mật khẩu
5. Kết quả hiển thị ngay:
   - **Thành công**: Hiển thị tên mạng và IP
   - **Sai mật khẩu**: Hiển thị lỗi, thử lại ngay

### Đổi WiFi (đã kết nối)

Truy cập `http://<IP-thiết-bị>:8888` từ trình duyệt cùng mạng WiFi, bấm **"Đổi mạng WiFi"**.

### Sau khi khởi động lại

Thiết bị tự kết nối WiFi đã lưu. Nếu WiFi không khả dụng, AP sẽ tự phát lại.

## Cấu trúc project

```
├── setup-openclawbox-wifi.sh       # Script cài đặt
├── captive-portal/
│   └── captive_portal.py           # Captive portal Python (AP+STA)
├── wifi-switch/
│   └── server.py                   # Service đổi WiFi qua browser
├── ui-custom/
│   └── index.html                  # Giao diện captive portal
└── README.md
```

## Kiến trúc

```
┌─────────────────────────────────────────────┐
│              WiFi Chipset (phy0)             │
│                                             │
│  ┌──────────────┐    ┌───────────────────┐  │
│  │  wlp3s0 (STA)│    │ wlp3s0ap (AP)     │  │
│  │  nmcli wifi  │    │ hostapd + dnsmasq  │  │
│  │  connect     │    │ SSID: OpenClawBox  │  │
│  └──────────────┘    │ Setup             │  │
│                      │ Portal: :8080      │  │
│                      └───────────────────┘  │
└─────────────────────────────────────────────┘
```

- **wlp3s0 (STA)**: Kết nối WiFi qua NetworkManager/nmcli
- **wlp3s0ap (AP)**: Virtual interface chạy hostapd + dnsmasq, phục vụ captive portal
- Cả hai chạy đồng thời trên cùng chip WiFi (cùng channel)

## Gỡ lỗi

```bash
# Kiểm tra chipset hỗ trợ AP+STA
iw list | grep -A 8 "valid interface"

# Kiểm tra interfaces
iw dev

# Kiểm tra NetworkManager
nmcli device status

# Xem log captive portal
sudo journalctl -u openclawbox-wifi.service -f

# Xem log WiFi switch
sudo journalctl -u openclawbox-wifi-switch.service -f

# Xóa WiFi đã lưu (để test lại)
nmcli connection delete "Tên_WiFi"

# Khởi động lại portal
sudo systemctl restart openclawbox-wifi.service
```

## Services

| Service | Port | Mô tả |
|---------|------|--------|
| `openclawbox-wifi.service` | 8080 (trên AP) | Captive portal cài đặt WiFi |
| `openclawbox-wifi-switch.service` | 8888 (trên LAN) | Đổi WiFi từ trình duyệt |

## Liên hệ

- Zalo: [0868287651](https://zalo.me/0868287651)
- Website: [openclaw-box.com](https://openclaw-box.com)
- Tài liệu: [docs.openclaw-box.com](https://docs.openclaw-box.com)

## License

Apache License 2.0
