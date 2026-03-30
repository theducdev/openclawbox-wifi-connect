const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const UI_DIR = path.join(__dirname, 'ui-custom');

// Mock WiFi networks (giả lập danh sách WiFi xung quanh)
const mockNetworks = [
  { ssid: 'TechLa_Office_5G', security: 'wpa2' },
  { ssid: 'TechLa_Office_2.4G', security: 'wpa2' },
  { ssid: 'Home_WiFi', security: 'wpa2' },
  { ssid: 'CoffeeShop_Free', security: 'open' },
  { ssid: 'Neighbor_Network', security: 'wpa2' },
  { ssid: 'Enterprise_Corp', security: 'enterprise' },
  { ssid: 'iPhone_Hotspot', security: 'wpa2' },
];

// Saved WiFi config
let savedConfig = null;

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.map': 'application/json',
  '.txt': 'text/plain',
};

function serveStatic(res, filePath) {
  const ext = path.extname(filePath);
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      // Fallback to index.html for SPA routing
      fs.readFile(path.join(UI_DIR, 'index.html'), (err2, indexData) => {
        if (err2) {
          res.writeHead(404);
          res.end('Not found');
          return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(indexData);
      });
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API: GET /networks
  if (req.method === 'GET' && req.url === '/networks') {
    console.log('[API] GET /networks - Returning mock WiFi list');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(mockNetworks));
    return;
  }

  // API: POST /connect
  if (req.method === 'POST' && req.url === '/connect') {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        savedConfig = data;
        console.log('[API] POST /connect - WiFi config received:');
        console.log(`       SSID: ${data.ssid}`);
        console.log(`       Identity: ${data.identity || '(none)'}`);
        console.log(`       Passphrase: ${'*'.repeat((data.passphrase || '').length)}`);
        console.log('[OK] Config saved! In real device, WiFi would connect now.');
        res.writeHead(200);
        res.end('OK');
      } catch (e) {
        console.error('[ERROR] Invalid JSON:', e.message);
        res.writeHead(400);
        res.end('Bad Request');
      }
    });
    return;
  }

  // API: GET /status (bonus - xem config đã lưu)
  if (req.method === 'GET' && req.url === '/status') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ saved: savedConfig }));
    return;
  }

  // Serve static UI files
  let filePath = req.url === '/' ? '/index.html' : req.url;
  serveStatic(res, path.join(UI_DIR, filePath));
});

server.listen(PORT, () => {
  console.log('='.repeat(50));
  console.log('  WiFi Connect - Mock Server');
  console.log('='.repeat(50));
  console.log(`  UI:       http://localhost:${PORT}`);
  console.log(`  Networks: http://localhost:${PORT}/networks`);
  console.log(`  Status:   http://localhost:${PORT}/status`);
  console.log('='.repeat(50));
  console.log('  Mock WiFi networks loaded:', mockNetworks.length);
  console.log('  Waiting for connections...');
  console.log('');
});
