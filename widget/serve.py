"""Local dev server for the QFix widget demo.

Serves static files and proxies API calls to avoid CORS issues
before the API has flask-cors deployed.

Usage: python3 serve.py
Then open http://localhost:8888/demo/
"""

import http.server
import urllib.request
import json

API_BASE = "https://kappahl-qfix.fly.dev"
PORT = 8888


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Proxy API calls matching /<brand>/product/<id>
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[1] == "product":
            try:
                api_key = self.headers.get("X-API-Key")
                if api_key:
                    url = f"{API_BASE}/{parts[0]}/product/{parts[2]}"
                    req = urllib.request.Request(url)
                    req.add_header("X-API-Key", api_key)
                else:
                    url = f"{API_BASE}/v4/product/{parts[2]}"
                    req = urllib.request.Request(url)
                with urllib.request.urlopen(req) as resp:
                    data = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        return super().do_GET()


if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), Handler)
    print(f"Serving at http://localhost:{PORT}")
    print(f"Open http://localhost:{PORT}/demo/ to view the demo")
    server.serve_forever()
