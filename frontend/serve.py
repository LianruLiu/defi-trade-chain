"""
    python frontend/serve.py
Serves this directory on http://localhost:5173 — plain static file
server, no build step (the frontend is vanilla JS on purpose).
"""
import http.server
import socketserver
from pathlib import Path

PORT = 5173
import os
os.chdir(Path(__file__).parent)

with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"serving frontend at http://localhost:{PORT}")
    httpd.serve_forever()
