# OpenClawBox WiFi Connect

Giao diện cài đặt WiFi tuỳ chỉnh cho thiết bị OpenClawBox, dựa trên [balena-os/wifi-connect](https://github.com/balena-os/wifi-connect).

Khi thiết bị chưa kết nối WiFi, nó sẽ phát một mạng Access Point với captive portal cho phép người dùng chọn mạng WiFi và nhập mật khẩu từ điện thoại hoặc laptop.

## Cách hoạt động

1. Thiết bị tạo Access Point (mặc định SSID: `WiFi Connect`)
2. Người dùng kết nối điện thoại/laptop vào Access Point
3. Captive portal hiển thị giao diện cài đặt WiFi (tiếng Việt)
4. Người dùng chọn mạng WiFi và nhập mật khẩu
5. Thiết bị kết nối vào mạng WiFi đã chọn, cấu hình được lưu tự động

## Cài đặt trên balenaOS

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

### Biến môi trường

| Biến | Mô tả | Mặc định |
|------|--------|----------|
| `PORTAL_SSID` | Tên mạng Access Point | `WiFi Connect` |
| `PORTAL_PASSPHRASE` | Mật khẩu Access Point (nếu muốn bảo vệ) | _(không có)_ |
| `UI_DIRECTORY` | Đường dẫn thư mục giao diện | `ui` |

## Phát triển

Chạy mock server để test giao diện locally:

```bash
node mock-server.js
```

Mở trình duyệt tại `http://localhost:3000`

## Giao diện tuỳ chỉnh

Giao diện nằm tại `ui-custom/index.html` - file HTML đơn với CSS và JS inline, hiển thị tiếng Việt có dấu.

## Liên hệ

- Zalo: [0868287651](https://zalo.me/0868287651)
- Website: [openclaw-box.com](https://openclaw-box.com)
- Tài liệu: [docs.openclaw-box.com](https://docs.openclaw-box.com)

## License

Dựa trên [wifi-connect](https://github.com/balena-os/wifi-connect) của balena.io, phân phối theo [Apache License 2.0](./LICENSE).
