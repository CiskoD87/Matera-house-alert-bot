import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Matera House Bot is running 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, format, *args):
        # Disabilita log spam per i ping periodici di UptimeRobot
        return

def run_http_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"[KeepAlive] Web server per UptimeRobot attivo sulla porta {port}")
    server.serve_forever()

def start_keep_alive():
    """Avvia il web server in un thread separato in background."""
    port = int(os.getenv("PORT", 8080))
    t = threading.Thread(target=run_http_server, args=(port,), daemon=True)
    t.start()

if __name__ == "__main__":
    run_http_server()

