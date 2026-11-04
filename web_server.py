"""
Embedded HTTP Server for ESP32 MicroPython
Provides non-blocking socket handling, HTTP request routing, and REST APIs
for storage metrics, directory listing, and file management.
"""

import socket
import gc
import json
import time

from file_manager import (
    get_storage_info,
    list_directory,
    normalize_path,
    delete_item
)


def parse_query_string(query_str):
    """Parse a URL query string (e.g., 'path=%2Flib&foo=bar') into a dict."""
    params = {}
    if not query_str:
        return params

    for pair in query_str.split("&"):
        if not pair:
            continue
        parts = pair.split("=", 1)
        key = unquote(parts[0])
        val = unquote(parts[1]) if len(parts) > 1 else ""
        params[key] = val
    return params


def unquote(string):
    """Decode percent-encoded URL characters (e.g., %20 -> space)."""
    if not string or "%" not in string:
        return string

    parts = string.split("%")
    res = parts[0]
    for item in parts[1:]:
        if len(item) >= 2:
            try:
                char_code = int(item[:2], 16)
                res += chr(char_code) + item[2:]
            except ValueError:
                res += "%" + item
        else:
            res += "%" + item
    return res


def send_response(client, status_code, content_type, body_bytes, extra_headers=None):
    """Send an HTTP response with headers and payload to client socket."""
    status_messages = {
        200: "OK",
        201: "Created",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error"
    }
    msg = status_messages.get(status_code, "OK")

    header = "HTTP/1.1 {} {}\r\n".format(status_code, msg)
    header += "Content-Type: {}\r\n".format(content_type)
    header += "Content-Length: {}\r\n".format(len(body_bytes))
    header += "Connection: close\r\n"
    header += "Access-Control-Allow-Origin: *\r\n"
    header += "Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\n"

    if extra_headers:
        for k, v in extra_headers.items():
            header += "{}: {}\r\n".format(k, v)

    header += "\r\n"

    try:
        client.write(header.encode("utf-8"))
        if body_bytes:
            client.write(body_bytes)
    except Exception as e:
        print("[HTTP] Socket write error: {}".format(e))


def send_json(client, data, status_code=200):
    """Serialize data dict to JSON and send response."""
    payload = json.dumps(data).encode("utf-8")
    send_response(client, status_code, "application/json; charset=utf-8", payload)


def send_error(client, status_code, message):
    """Send a structured JSON error response."""
    send_json(client, {"error": message, "status": status_code}, status_code=status_code)


def handle_get_storage(client):
    """API handler: GET /api/storage"""
    info = get_storage_info()
    send_json(client, info)


def handle_get_files(client, query_params):
    """API handler: GET /api/files?path=/..."""
    target_path = query_params.get("path", "/")
    entries = list_directory(target_path)

    if entries is None:
        send_error(client, 404, "Directory '{}' not found".format(target_path))
        return

    send_json(client, {
        "path": normalize_path(target_path),
        "entries": entries
    })


def handle_delete_file(client, query_params):
    """API handler: DELETE /api/files?path=/..."""
    target_path = query_params.get("path", "")
    if not target_path or target_path == "/":
        send_error(client, 400, "Invalid path for deletion")
        return

    success = delete_item(target_path)
    if success:
        send_json(client, {"success": True, "deleted": normalize_path(target_path)})
    else:
        send_error(client, 500, "Failed to delete '{}'".format(target_path))


def handle_status_page(client, ip_address):
    """Temporary status page for root GET / until UI is integrated."""
    storage = get_storage_info()
    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 File Transfer Tool</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; max-width: 500px; margin: 0 auto; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
    h1 {{ font-size: 1.25rem; color: #38bdf8; margin-top: 0; }}
    .stat {{ display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155; }}
    .badge {{ background: #0284c7; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; }}
    a {{ color: #38bdf8; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>ESP32 File Transfer Server</h1>
    <div class="stat"><span>Server Status:</span><span class="badge">Running</span></div>
    <div class="stat"><span>IP Address:</span><span>{}</span></div>
    <div class="stat"><span>Total Storage:</span><span>{} MB</span></div>
    <div class="stat"><span>Free Storage:</span><span>{} MB</span></div>
    <div class="stat"><span>Storage Used:</span><span>{}%</span></div>
    <p style="margin-top:1.5rem; font-size: 0.9rem; color: #94a3b8;">
      Available API Endpoints:<br>
      &bull; <a href="/api/storage">/api/storage</a><br>
      &bull; <a href="/api/files?path=/">/api/files?path=/</a>
    </p>
  </div>
</body>
</html>""".format(
        ip_address,
        storage["total_mb"],
        storage["free_mb"],
        storage["used_pct"]
    )
    send_response(client, 200, "text/html; charset=utf-8", html.encode("utf-8"))


def route_request(client, raw_request, ip_address="192.168.4.1"):
    """Parse HTTP request method, path, and dispatch to appropriate handler."""
    lines = raw_request.split("\r\n")
    if not lines or not lines[0]:
        return

    request_line = lines[0].split()
    if len(request_line) < 2:
        return

    method = request_line[0].upper()
    url = request_line[1]

    # Handle CORS preflight OPTIONS request
    if method == "OPTIONS":
        send_response(client, 200, "text/plain", b"")
        return

    # Split path and query string
    if "?" in url:
        path, query_str = url.split("?", 1)
    else:
        path, query_str = url, ""

    query_params = parse_query_string(query_str)
    print("[HTTP] {} {}".format(method, path))

    # Route dispatch
    if method == "GET" and path == "/":
        handle_status_page(client, ip_address)
    elif method == "GET" and path == "/api/storage":
        handle_get_storage(client)
    elif method == "GET" and path == "/api/files":
        handle_get_files(client, query_params)
    elif method == "DELETE" and path == "/api/files":
        handle_delete_file(client, query_params)
    else:
        send_error(client, 404, "Endpoint '{}' not found".format(path))


def start_server(ip_address="0.0.0.0", port=80):
    """
    Start the embedded HTTP server listener loop.
    Accepts connections, processes requests, and reclaims memory.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow port reuse immediately after restarts
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind(("0.0.0.0", port))
        server_socket.listen(5)
        print("[HTTP] Server listening on http://{}:{}/".format(ip_address, port))

        while True:
            try:
                client_sock, client_addr = server_socket.accept()
                client_sock.settimeout(3.0)

                # Read first line / header chunk
                raw_data = b""
                try:
                    raw_data = client_sock.recv(1024)
                except OSError:
                    pass

                if raw_data:
                    request_text = raw_data.decode("utf-8", "ignore")
                    route_request(client_sock, request_text, ip_address)

                client_sock.close()
            except OSError as e:
                # Socket timeout or client reset
                pass
            except Exception as e:
                print("[HTTP] Client processing error: {}".format(e))
            finally:
                gc.collect()

    except Exception as e:
        print("[HTTP] Server fatal error: {}".format(e))
    finally:
        server_socket.close()
        print("[HTTP] Server closed.")


if __name__ == "__main__":
    from wifi_manager import setup_network
    print("=== ESP32 Web Server Self-Test ===")
    net = setup_network()
    ip = net["ip"]
    start_server(ip_address=ip, port=80)

