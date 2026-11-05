"""
DNS Subsystem for Access Point (AP) Mode
Provides a lightweight UDP DNS server (port 53) that resolves all local hostnames
(e.g., 'esp32', 'esp32.local', 'transfer.local') directly to the ESP32 IP address.
"""

import socket


class DNSServer:
    """Lightweight non-blocking DNS responder for AP mode captive portal / local domain resolution."""

    def __init__(self, ip_address="192.168.4.1", port=53):
        self.ip_address = ip_address
        self.port = port
        self.ip_bytes = bytes(map(int, ip_address.split(".")))
        self.sock = None

    def start(self):
        """Bind non-blocking UDP socket on port 53."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
            self.sock.bind(("0.0.0.0", self.port))
            print("[DNS] Active on port {} (resolving local names to {})".format(self.port, self.ip_address))
            return True
        except Exception as e:
            print("[DNS] Note: Could not bind port {} ({})".format(self.port, e))
            self.sock = None
            return False

    def process(self):
        """Check for and answer any pending DNS requests."""
        if not self.sock:
            return

        # Handle up to 3 queries per cycle without blocking
        for _ in range(3):
            try:
                data, addr = self.sock.recvfrom(256)
                if len(data) < 12:
                    continue

                # Build DNS response packet:
                # - Transaction ID: data[:2]
                # - Flags: 0x8180 (Response, Opcode: Query, Authoritative, Recursion Allowed, No Error)
                # - Questions: data[4:6], Answer RRs: 1, Authority RRs: 0, Additional RRs: 0
                # - Question section: data[12:]
                # - Answer section:
                #     Name pointer: 0xc00c (points to domain name in Question)
                #     Type: 0x0001 (Type A, IPv4)
                #     Class: 0x0001 (IN, Internet)
                #     TTL: 60 seconds (0x0000003c)
                #     Data length: 4 bytes (0x0004)
                #     IP address: 4 bytes (e.g. 192.168.4.1)
                response = (
                    data[:2] +
                    b"\x81\x80" +
                    data[4:6] +
                    b"\x00\x01\x00\x00\x00\x00" +
                    data[12:] +
                    b"\xc0\x0c" +
                    b"\x00\x01\x00\x01" +
                    b"\x00\x00\x00\x3c" +
                    b"\x00\x04" +
                    self.ip_bytes
                )
                self.sock.sendto(response, addr)
            except OSError:
                # No data ready (EAGAIN / EWOULDBLOCK)
                break
            except Exception:
                break

    def stop(self):
        """Close socket cleanly."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

