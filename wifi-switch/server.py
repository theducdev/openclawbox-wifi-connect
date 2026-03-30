#!/usr/bin/env python3
"""Simple HTTP server to allow switching WiFi via browser."""

import subprocess
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler

HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenClawBox - Đổi WiFi</title>
  <style>
    :root { --primary: #b83240; --bg: #0f0f13; --bg-card: #1a1a24; --text: #f0f0f5; --text-muted: #9090a0; --border: #2d2d3d; }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 32px; max-width: 400px; width: 90%%; text-align: center; }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h2 { font-size: 20px; margin-bottom: 8px; }
    .ssid { color: var(--primary); font-weight: 600; }
    p { font-size: 14px; color: var(--text-muted); line-height: 1.6; margin-bottom: 24px; }
    .btn { display: inline-block; padding: 14px 32px; background: var(--primary); color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; text-decoration: none; transition: opacity 0.2s; }
    .btn:hover { opacity: 0.9; }
    .btn:active { transform: scale(0.98); }
    .msg { margin-top: 20px; padding: 12px; border-radius: 8px; font-size: 14px; display: none; }
    .msg.show { display: block; }
    .msg-info { background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); color: #60a5fa; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="#b83240" stroke-width="2" stroke-linecap="round">
        <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="#b83240"/>
      </svg>
    </div>
    <h2>WiFi hiện tại</h2>
    <p>Đang kết nối: <span class="ssid">%s</span></p>
    <button class="btn" onclick="switchWifi()">Đổi mạng WiFi</button>
    <div id="msg" class="msg msg-info">
      Đang chuyển sang chế độ cài đặt WiFi...<br>
      Hãy kết nối vào mạng <strong>"OpenClawBox Setup"</strong> và mở <strong>192.168.42.1:8080</strong> để chọn WiFi mới.
    </div>
  </div>
  <script>
    function switchWifi() {
      document.getElementById('msg').classList.add('show');
      document.querySelector('.btn').disabled = true;
      document.querySelector('.btn').style.opacity = '0.5';
      fetch('/switch', { method: 'POST' }).catch(() => {});
    }
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ssid = self._get_ssid()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write((HTML_PAGE % ssid).encode())

    def do_POST(self):
        if self.path == '/switch':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            subprocess.Popen(
                ['bash', '-c', 'sleep 2 && nmcli device disconnect wlp3s0 && systemctl restart openclawbox-wifi.service'],
            )
        else:
            self.send_response(404)
            self.end_headers()

    def _get_ssid(self):
        try:
            return subprocess.check_output(['iwgetid', '-r']).decode().strip() or 'Không xác định'
        except Exception:
            return 'Chưa kết nối'

    def log_message(self, format, *args):
        pass


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '0.0.0.0'


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8888), Handler)
    ip = get_local_ip()
    print(f'WiFi Switch server running on http://{ip}:8888')
    server.serve_forever()
