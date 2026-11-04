"""
Embedded HTTP Server for ESP32 MicroPython
Provides non-blocking socket handling, HTTP request routing, REST APIs,
and chunked streaming for RAM-safe file downloads and uploads.
"""

import socket
import gc
import json
import os
import time

from file_manager import (
    get_storage_info,
    list_directory,
    normalize_path,
    join_path,
    get_parent_dir,
    ensure_directory,
    delete_item
)

CHUNK_SIZE = 1024


def parse_query_string(query_str):
    """Parse a URL query string into a dict."""
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
    """Decode percent-encoded URL characters."""
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
        413: "Payload Too Large",
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


def handle_download_file(client, query_params):
    """
    API handler: GET /api/download?path=/...
    Streams requested file in small chunks directly to socket.
    """
    raw_path = query_params.get("path", "")
    if not raw_path or raw_path == "/":
        send_error(client, 400, "Path parameter is required")
        return

    target = normalize_path(raw_path)
    try:
        stat = os.stat(target)
        # Check if directory
        if stat[0] & 0x4000:
            send_error(client, 400, "Cannot download a directory")
            return
        file_size = stat[6]
    except OSError:
        send_error(client, 404, "File not found: '{}'".format(target))
        return

    filename = target.split("/")[-1]
    header = "HTTP/1.1 200 OK\r\n"
    header += "Content-Type: application/octet-stream\r\n"
    header += "Content-Length: {}\r\n".format(file_size)
    header += "Content-Disposition: attachment; filename=\"{}\"\r\n".format(filename)
    header += "Connection: close\r\n"
    header += "Access-Control-Allow-Origin: *\r\n\r\n"

    try:
        client.write(header.encode("utf-8"))
        with open(target, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                client.write(chunk)
        print("[HTTP] Streamed download: '{}' ({} bytes)".format(target, file_size))
    except Exception as e:
        print("[HTTP] Download streaming error: {}".format(e))
    finally:
        gc.collect()


def handle_upload_file(client, query_params, headers, initial_body, client_sock):
    """
    API handler: POST /api/upload?path=/...
    Streams incoming binary file in chunks directly into a temporary file (.upload.tmp).
    Atomic rename to final path upon 100% complete byte verification.
    """
    raw_path = query_params.get("path", "")
    if not raw_path or raw_path == "/":
        send_error(client, 400, "Destination path parameter is required")
        return

    target = normalize_path(raw_path)
    content_length = int(headers.get("content-length", 0))

    if content_length <= 0:
        send_error(client, 400, "Content-Length header required and must be > 0")
        return

    # Check available storage
    storage = get_storage_info()
    if content_length > (storage["free_bytes"] - 4096):
        send_error(client, 413, "Insufficient flash storage ({} bytes needed, {} free)".format(
            content_length, storage["free_bytes"]
        ))
        return

    # Ensure parent directory exists
    parent = get_parent_dir(target)
    if parent != "/" and not ensure_directory(parent):
        send_error(client, 500, "Failed to create directory structure for '{}'".format(parent))
        return

    temp_path = target + ".upload.tmp"
    bytes_written = 0

    print("[HTTP] Upload starting: '{}' ({} bytes expected)".format(target, content_length))

    try:
        with open(temp_path, "wb") as f:
            # Write any initial body bytes that came with the header chunk
            if initial_body:
                f.write(initial_body)
                bytes_written += len(initial_body)

            # Stream remaining bytes in chunks
            while bytes_written < content_length:
                remaining = content_length - bytes_written
                read_size = CHUNK_SIZE if remaining > CHUNK_SIZE else remaining
                chunk = client_sock.recv(read_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)

        # Verify integrity
        if bytes_written == content_length:
            # Remove existing file if replacing
            try:
                os.remove(target)
            except OSError:
                pass
            os.rename(temp_path, target)
            print("[HTTP] Upload completed successfully: '{}' ({} bytes)".format(target, bytes_written))
            send_json(client, {
                "success": True,
                "path": target,
                "size": bytes_written
            }, status_code=201)
        else:
            print("[HTTP] Upload incomplete (got {} of {} bytes)".format(bytes_written, content_length))
            try:
                os.remove(temp_path)
            except OSError:
                pass
            send_error(client, 500, "Upload interrupted: received {}/{} bytes".format(bytes_written, content_length))

    except Exception as e:
        print("[HTTP] Upload exception: {}".format(e))
        try:
            os.remove(temp_path)
        except OSError:
            pass
        send_error(client, 500, "File write error: {}".format(e))
    finally:
        gc.collect()


def handle_status_page(client, ip_address):
    """Status dashboard with interactive file table and live upload test form."""
    storage = get_storage_info()
    files = list_directory("/") or []

    rows = ""
    for f in files:
        kind = "📁 Dir" if f["is_dir"] else "📄 File"
        size = "-" if f["is_dir"] else "{} B".format(f["size"])
        actions = ""
        if not f["is_dir"]:
            actions += '<a href="/api/download?path=/{}" class="btn">⬇ Download</a> '.format(f["name"])
        actions += '<button onclick="delFile(\'/{}\')" class="btn btn-del">🗑 Delete</button>'.format(f["name"])

        rows += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            kind, f["name"], size, actions
        )

    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 File Transfer</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 1.5rem; }}
    .container {{ max-width: 700px; margin: 0 auto; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }}
    h1 {{ font-size: 1.25rem; color: #38bdf8; margin: 0 0 1rem 0; }}
    .stat {{ display: flex; justify-content: space-between; padding: 0.35rem 0; font-size: 0.95rem; border-bottom: 1px solid #334155; }}
    .badge {{ background: #0284c7; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }}
    th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ color: #94a3b8; font-weight: 500; }}
    .btn {{ background: #0284c7; color: white; border: none; padding: 4px 8px; border-radius: 4px; text-decoration: none; cursor: pointer; font-size: 0.8rem; display: inline-block; }}
    .btn-del {{ background: #ef4444; }}
    .dropzone {{ border: 2px dashed #475569; border-radius: 6px; padding: 1.5rem; text-align: center; cursor: pointer; }}
    .dropzone:hover {{ border-color: #38bdf8; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>ESP32 File Transfer</h1>
      <div class="stat"><span>IP Address:</span><span>{}</span></div>
      <div class="stat"><span>Storage:</span><span>{} MB free of {} MB ({}% used)</span></div>
    </div>

    <div class="card">
      <h1>Upload File</h1>
      <div class="dropzone" onclick="document.getElementById('fileInput').click()">
        <p id="dropText">Click or Drop a file here to upload to /</p>
        <input type="file" id="fileInput" style="display:none" onchange="uploadSelected(this.files)">
      </div>
      <div id="uploadStatus" style="margin-top:0.75rem; font-size:0.85rem; color:#38bdf8;"></div>
    </div>

    <div class="card">
      <h1>Files on Device (/)</h1>
      <table>
        <thead><tr><th>Type</th><th>Name</th><th>Size</th><th>Actions</th></tr></thead>
        <tbody>{}</tbody>
      </table>
    </div>
  </div>

  <script>
    async function uploadSelected(files) {{
      if (!files.length) return;
      const file = files[0];
      const status = document.getElementById('uploadStatus');
      status.innerText = 'Uploading ' + file.name + ' (' + file.size + ' bytes)...';
      try {{
        const res = await fetch('/api/upload?path=/' + encodeURIComponent(file.name), {{
          method: 'POST',
          body: file
        }});
        const json = await res.json();
        if (res.ok) {{
          status.innerText = '✅ Uploaded ' + file.name + ' successfully!';
          setTimeout(() => location.reload(), 1000);
        }} else {{
          status.innerText = '❌ Error: ' + (json.error || 'Upload failed');
        }}
      }} catch (err) {{
        status.innerText = '❌ Network error during upload';
      }}
    }}

    async function delFile(path) {{
      if (!confirm('Delete ' + path + '?')) return;
      const res = await fetch('/api/files?path=' + encodeURIComponent(path), {{ method: 'DELETE' }});
      if (res.ok) location.reload();
      else alert('Failed to delete file');
    }}
  </script>
</body>
</html>""".format(
        ip_address,
        storage["free_mb"],
        storage["total_mb"],
        storage["used_pct"],
        rows
    )
    send_response(client, 200, "text/html; charset=utf-8", html.encode("utf-8"))


def parse_headers_and_body(raw_chunk):
    """Split received HTTP socket chunk into request line, headers dict, and initial body bytes."""
    header_end = raw_chunk.find(b"\r\n\r\n")
    if header_end == -1:
        return "", {}, b""

    header_bytes = raw_chunk[:header_end]
    initial_body = raw_chunk[header_end + 4:]

    header_text = header_bytes.decode("utf-8", "ignore")
    lines = header_text.split("\r\n")
    request_line = lines[0] if lines else ""

    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return request_line, headers, initial_body


def route_request(client, raw_chunk, ip_address="192.168.4.1"):
    """Parse HTTP request and dispatch to handlers."""
    request_line, headers, initial_body = parse_headers_and_body(raw_chunk)
    if not request_line:
        return

    parts = request_line.split()
    if len(parts) < 2:
        return

    method = parts[0].upper()
    url = parts[1]

    # Handle CORS preflight
    if method == "OPTIONS":
        send_response(client, 200, "text/plain", b"")
        return

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
    elif method == "GET" and path == "/api/download":
        handle_download_file(client, query_params)
    elif method == "POST" and path == "/api/upload":
        handle_upload_file(client, query_params, headers, initial_body, client)
    elif method == "DELETE" and path == "/api/files":
        handle_delete_file(client, query_params)
    else:
        send_error(client, 404, "Endpoint '{}' not found".format(path))


def start_server(ip_address="0.0.0.0", port=80):
    """Embedded HTTP server listener loop."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind(("0.0.0.0", port))
        server_socket.listen(5)
        print("[HTTP] Server listening on http://{}:{}/".format(ip_address, port))

        while True:
            try:
                client_sock, client_addr = server_socket.accept()
                client_sock.settimeout(5.0)

                raw_chunk = b""
                try:
                    raw_chunk = client_sock.recv(1024)
                except OSError:
                    pass

                if raw_chunk:
                    route_request(client_sock, raw_chunk, ip_address)

                client_sock.close()
            except OSError:
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
