"""
HTTP Application Server Subsystem
Provides robust non-blocking HTTP socket listener, REST routing,
and streaming of both static assets and binary file transfers.
"""

import socket
import gc
import json
import os
import time

from app.storage import StorageManager
from app.dns import DNSServer


class WebServer:
    """Production-grade embedded HTTP server with streaming I/O and REST API."""

    def __init__(self, config, ip_address="0.0.0.0", hostname="esp32"):
        srv_cfg = config.get("server", {})
        self.port = srv_cfg.get("port", 80)
        self.chunk_size = srv_cfg.get("chunk_size", 1024)
        self.static_dir = srv_cfg.get("static_dir", "www")
        self.ip_address = ip_address
        self.hostname = hostname
        self.running = False

    def start(self):
        """Bind socket and enter continuous request handling loop."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        dns = DNSServer(ip_address=self.ip_address, port=53)
        dns.start()

        try:
            server_sock.bind(("0.0.0.0", self.port))
            server_sock.listen(5)
            # Use small timeout on accept so DNS loop remains responsive
            server_sock.settimeout(0.2)
            self.running = True
            print("[Server] Listening at http://{}:{}/ (or http://{}/, http://{}.local/)".format(
                self.ip_address, self.port, self.hostname, self.hostname
            ))

            while self.running:
                # Service any pending DNS queries
                dns.process()

                try:
                    client_sock, client_addr = server_sock.accept()
                    client_sock.settimeout(5.0)

                    raw_chunk = b""
                    try:
                        raw_chunk = client_sock.recv(self.chunk_size)
                    except OSError:
                        pass

                    if raw_chunk:
                        self._dispatch_request(client_sock, raw_chunk)

                    client_sock.close()
                except OSError:
                    # Timeout on accept, loop continues to service DNS
                    pass
                except Exception as e:
                    print("[Server] Request error: {}".format(e))
                finally:
                    gc.collect()

        except Exception as e:
            print("[Server] Fatal error: {}".format(e))
        finally:
            dns.stop()
            server_sock.close()
            self.running = False
            print("[Server] Stopped.")

    def _dispatch_request(self, client, raw_chunk):
        """Parse HTTP headers and route to the registered handler."""
        request_line, headers, initial_body = self._parse_request_header(raw_chunk)
        if not request_line:
            return

        parts = request_line.split()
        if len(parts) < 2:
            return

        method = parts[0].upper()
        url = parts[1]

        if method == "OPTIONS":
            self._send_response(client, 200, "text/plain", b"")
            return

        if "?" in url:
            path, query_str = url.split("?", 1)
        else:
            path, query_str = url, ""

        # Handle Windows / Android connectivity probes silently to stop log spam
        if path == "/connecttest.txt":
            self._send_response(client, 200, "text/plain", b"Microsoft Connect Test")
            return
        elif path in ("/generate_204", "/gen_204"):
            self._send_response(client, 204, "text/plain", b"")
            return
        elif path == "/favicon.ico":
            self._send_response(client, 204, "image/x-icon", b"")
            return

        query_params = self._parse_query_string(query_str)
        print("[HTTP] {} {}".format(method, path))

        # Route table
        if method == "GET" and path == "/":
            self._serve_index(client)
        elif method == "GET" and path == "/api/storage":
            self._handle_get_storage(client)
        elif method == "GET" and path == "/api/files":
            self._handle_get_files(client, query_params)
        elif method == "POST" and path == "/api/mkdir":
            self._handle_create_directory(client, query_params)
        elif method == "GET" and path == "/api/download":
            self._handle_download(client, query_params)
        elif method == "GET" and path == "/api/hash":
            self._handle_get_hash(client, query_params)
        elif method == "POST" and path == "/api/upload":
            self._handle_upload(client, query_params, headers, initial_body)
        elif method == "DELETE" and path == "/api/files":
            self._handle_delete(client, query_params)
        else:
            self._send_error(client, 404, "Endpoint '{}' not found".format(path))

    def _serve_index(self, client):
        """Stream www/index.html directly from flash to save RAM."""
        index_path = self.static_dir + "/index.html"
        try:
            stat = os.stat(index_path)
            file_size = stat[6]
        except OSError:
            self._send_error(client, 500, "Web asset 'www/index.html' not found on ESP32 flash")
            return

        header = "HTTP/1.1 200 OK\r\n"
        header += "Content-Type: text/html; charset=utf-8\r\n"
        header += "Content-Length: {}\r\n"
        header += "Cache-Control: no-cache, no-store, must-revalidate\r\n"
        header += "Pragma: no-cache\r\n"
        header += "Connection: close\r\n\r\n"
        header = header.format(file_size)

        try:
            client.write(header.encode("utf-8"))
            with open(index_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    client.write(chunk)
        except Exception as e:
            print("[Server] Error streaming index.html: {}".format(e))
        finally:
            gc.collect()

    def _handle_get_storage(self, client):
        """API handler: GET /api/storage"""
        metrics = StorageManager.get_metrics("/")
        self._send_json(client, metrics)

    def _handle_get_files(self, client, query_params):
        """API handler: GET /api/files?path=/..."""
        target = query_params.get("path", "/")
        entries = StorageManager.list_dir(target)
        if entries is None:
            self._send_error(client, 404, "Directory '{}' not found".format(target))
            return

        self._send_json(client, {
            "path": StorageManager.normalize_path(target),
            "entries": entries
        })

    def _handle_create_directory(self, client, query_params):
        """API handler: POST /api/mkdir?path=/..."""
        target = query_params.get("path", "")
        if not target or target == "/":
            self._send_error(client, 400, "Directory path parameter required")
            return

        if StorageManager.make_dir(target):
            self._send_json(client, {"success": True, "path": StorageManager.normalize_path(target)}, status_code=201)
        else:
            self._send_error(client, 500, "Failed to create directory")

    def _handle_delete(self, client, query_params):
        """API handler: DELETE /api/files?path=/..."""
        target = query_params.get("path", "")
        if not target or target == "/":
            self._send_error(client, 400, "Path parameter required")
            return

        if StorageManager.delete(target):
            self._send_json(client, {"success": True, "deleted": StorageManager.normalize_path(target)})
        else:
            self._send_error(client, 500, "Failed to delete item")

    def _handle_download(self, client, query_params):
        """API handler: GET /api/download?path=/..."""
        raw_path = query_params.get("path", "")
        if not raw_path or raw_path == "/":
            self._send_error(client, 400, "Path parameter required")
            return

        target = StorageManager.normalize_path(raw_path)
        try:
            stat = os.stat(target)
            if stat[0] & 0x4000:
                self._send_error(client, 400, "Cannot download a directory")
                return
            file_size = stat[6]
        except OSError:
            self._send_error(client, 404, "File not found")
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
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    client.write(chunk)
            print("[Server] Download streamed: '{}' ({} bytes)".format(target, file_size))
        except Exception as e:
            print("[Server] Error streaming download: {}".format(e))
        finally:
            gc.collect()

    def _handle_get_hash(self, client, query_params):
        """API handler: GET /api/hash?path=/... (Returns SHA-256 and size for integrity check)."""
        raw_path = query_params.get("path", "")
        if not raw_path or raw_path == "/":
            self._send_error(client, 400, "Path parameter required")
            return

        target = StorageManager.normalize_path(raw_path)
        try:
            stat = os.stat(target)
            file_size = stat[6]
            digest = StorageManager.compute_sha256(target)
            if digest is None:
                self._send_error(client, 404, "File not found")
                return

            self._send_json(client, {"path": target, "sha256": digest, "size": file_size})
        except OSError:
            self._send_error(client, 404, "File not found")
        finally:
            gc.collect()

    def _handle_upload(self, client, query_params, headers, initial_body):
        """API handler: POST /api/upload?path=/..."""
        raw_path = query_params.get("path", "")
        if not raw_path or raw_path == "/":
            self._send_error(client, 400, "Destination path parameter required")
            return

        target = StorageManager.normalize_path(raw_path)
        allow_overwrite = query_params.get("overwrite", "false").lower() == "true"

        if not allow_overwrite and StorageManager.exists(target):
            self._send_error(client, 409, "File '{}' already exists".format(target))
            return

        content_length = int(headers.get("content-length", 0))

        if content_length <= 0:
            self._send_error(client, 400, "Content-Length header required and must be > 0")
            return

        metrics = StorageManager.get_metrics("/")
        if content_length > (metrics["free_bytes"] - 4096):
            self._send_error(client, 413, "Insufficient storage ({} bytes needed, {} free)".format(
                content_length, metrics["free_bytes"]
            ))
            return

        print("[Server] Upload start: '{}' ({} bytes)".format(target, content_length))
        ok, written, err = StorageManager.write_stream(
            target, content_length, client, initial_body, self.chunk_size
        )

        if ok:
            print("[Server] Upload success: '{}' ({} bytes)".format(target, written))
            self._send_json(client, {"success": True, "path": target, "size": written}, status_code=201)
        else:
            print("[Server] Upload failed: {}".format(err))
            self._send_error(client, 500, err)

    def _send_response(self, client, status_code, content_type, body_bytes, extra_headers=None):
        """Send formatted HTTP response."""
        status_messages = {
            200: "OK", 201: "Created", 400: "Bad Request",
            404: "Not Found", 413: "Payload Too Large", 500: "Internal Error"
        }
        msg = status_messages.get(status_code, "OK")

        hdr = "HTTP/1.1 {} {}\r\n".format(status_code, msg)
        hdr += "Content-Type: {}\r\n".format(content_type)
        hdr += "Content-Length: {}\r\n".format(len(body_bytes))
        hdr += "Connection: close\r\n"
        hdr += "Access-Control-Allow-Origin: *\r\n"

        if extra_headers:
            for k, v in extra_headers.items():
                hdr += "{}: {}\r\n".format(k, v)

        hdr += "\r\n"

        try:
            client.write(hdr.encode("utf-8"))
            if body_bytes:
                client.write(body_bytes)
        except Exception as e:
            print("[Server] Write error: {}".format(e))

    def _send_json(self, client, data, status_code=200):
        """Send JSON response."""
        body = json.dumps(data).encode("utf-8")
        self._send_response(client, status_code, "application/json; charset=utf-8", body)

    def _send_error(self, client, status_code, message):
        """Send JSON error response."""
        self._send_json(client, {"error": message, "status": status_code}, status_code=status_code)

    def _parse_query_string(self, query_str):
        """Parse query string into dict."""
        params = {}
        if not query_str:
            return params
        for pair in query_str.split("&"):
            if not pair:
                continue
            parts = pair.split("=", 1)
            k = self._unquote(parts[0])
            v = self._unquote(parts[1]) if len(parts) > 1 else ""
            params[k] = v
        return params

    def _unquote(self, s):
        """Decode percent-encoded strings."""
        if not s or "%" not in s:
            return s
        parts = s.split("%")
        res = parts[0]
        for it in parts[1:]:
            if len(it) >= 2:
                try:
                    res += chr(int(it[:2], 16)) + it[2:]
                except ValueError:
                    res += "%" + it
            else:
                res += "%" + it
        return res

    def _parse_request_header(self, raw_chunk):
        """Split initial chunk into request line, headers dict, and initial body bytes."""
        idx = raw_chunk.find(b"\r\n\r\n")
        if idx == -1:
            return "", {}, b""

        hdr_bytes = raw_chunk[:idx]
        body_bytes = raw_chunk[idx + 4:]

        lines = hdr_bytes.decode("utf-8", "ignore").split("\r\n")
        req_line = lines[0] if lines else ""

        headers = {}
        for l in lines[1:]:
            if ":" in l:
                k, v = l.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        return req_line, headers, body_bytes

