#!/usr/bin/env python3
"""Мини-сервер: показывает актуальный QR для входа (http://<ip>:8081/)."""

from __future__ import annotations

import http.server
import socketserver
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data"
QR = BASE / "qr.png"

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="4">
<style>
 body{{background:#111;color:#eee;font-family:sans-serif;text-align:center;margin:0;padding:24px}}
 img{{width:360px;height:360px;image-rendering:pixelated;background:#fff;padding:14px;border-radius:14px}}
 h2{{font-weight:500;font-size:18px}} p{{color:#888}}
</style></head>
<body>
 <h2>Telegram → Настройки → Устройства → Подключить устройство</h2>
 <img src="/qr.png?t={ts}">
 <p>QR обновляется автоматически (t={ts})</p>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/qr.png"):
            if not QR.exists():
                self.send_error(404)
                return
            data = QR.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        body = PAGE.format(ts=int(time.time())).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: A003
        pass


class Reuse(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Reuse(("0.0.0.0", 8081), Handler) as httpd:
        print("QR server on :8081", flush=True)
        httpd.serve_forever()
