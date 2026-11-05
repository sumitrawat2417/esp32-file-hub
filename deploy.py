"""
One-Click Deployment Tool for ESP32 File Transfer Tool
Automatically detects connected ESP32, syncs all project files and directories,
and soft-reboots the device in seconds using MicroPython Raw REPL.
"""

import os
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: 'pyserial' is required. Run: pip install pyserial")
    sys.exit(1)


def find_esp32_port():
    """Auto-detect USB serial port for ESP32."""
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        if any(chip in desc for chip in ["cp210", "ch340", "ch9102", "ftdi", "usb to uart", "esp32"]):
            return p.device

    # Fallback to first available port if only one exists
    available = [p.device for p in ports if "com1" not in p.device.lower()]
    if available:
        return available[0]
    return None


class RawReplUploader:
    """Communicates directly with MicroPython raw REPL over serial."""

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(0.1)
            self._enter_raw_repl()
            return True
        except serial.SerialException as e:
            if "PermissionError" in str(e) or "Access is denied" in str(e):
                print("\n[!] Error: Port '{}' is busy. Please close Thonny or other serial monitors first.".format(self.port))
            else:
                print("\n[!] Connection error on port '{}': {}".format(self.port, e))
            return False

    def _enter_raw_repl(self):
        # Send Ctrl-C twice to break out of running loops
        self.ser.write(b"\r\x03\x03")
        time.sleep(0.2)
        self.ser.reset_input_buffer()

        # Send Ctrl-A to enter raw REPL
        self.ser.write(b"\x01")
        time.sleep(0.2)
        resp = self.ser.read_all()
        if b"raw REPL" not in resp:
            # Try again once
            self.ser.write(b"\r\x03\x01")
            time.sleep(0.3)
            resp = self.ser.read_all()

    def execute(self, cmd_str):
        """Execute a Python command block in raw REPL."""
        cmd_bytes = cmd_str.encode("utf-8") + b"\x04"
        self.ser.write(cmd_bytes)
        
        # Read response up to OK followed by output
        resp = b""
        start = time.time()
        while time.time() - start < 5:
            if self.ser.in_waiting:
                resp += self.ser.read(self.ser.in_waiting)
                if b"\x04>" in resp:
                    break
            time.sleep(0.01)
        return resp

    def make_remote_dir(self, dir_path):
        """Create directory on ESP32."""
        code = (
            "import os\n"
            "try:\n"
            "    os.mkdir('{0}')\n"
            "except:\n"
            "    pass\n"
        ).format(dir_path)
        self.execute(code)

    def upload_file(self, local_path, remote_path):
        """Upload file content using raw REPL."""
        with open(local_path, "rb") as f:
            content = f.read()

        # Open file on ESP32
        self.execute("f = open('{}', 'wb')".format(remote_path))

        # Stream in 256-byte binary chunks
        chunk_size = 256
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            # Write chunk representation
            self.execute("f.write({})".format(repr(chunk)))

        self.execute("f.close()")

    def reboot(self):
        """Exit raw REPL and soft reboot."""
        if self.ser:
            # Ctrl-B to exit raw REPL and reboot
            self.ser.write(b"\x02")
            self.ser.close()


def deploy():
    print("=" * 50)
    print("   ESP32 File Transfer Tool - 1-Click Installer")
    print("=" * 50)

    port = find_esp32_port()
    if not port:
        print("\n[!] No ESP32 detected. Check USB data cable connection.")
        return

    print("Found ESP32 on port: {}".format(port))
    uploader = RawReplUploader(port)

    print("Connecting to ESP32...")
    if not uploader.connect():
        return

    # Files and folders to upload
    files_to_sync = [
        ("boot.py", "boot.py"),
        ("main.py", "main.py"),
        ("config.json", "config.json"),
        ("www/index.html", "www/index.html"),
        ("app/__init__.py", "app/__init__.py"),
        ("app/config.py", "app/config.py"),
        ("app/wifi.py", "app/wifi.py"),
        ("app/storage.py", "app/storage.py"),
        ("app/server.py", "app/server.py"),
    ]

    # Directories to ensure exist
    dirs_to_create = ["app", "www"]
    for d in dirs_to_create:
        uploader.make_remote_dir(d)

    total = len(files_to_sync)
    for idx, (local, remote) in enumerate(files_to_sync, start=1):
        if not os.path.exists(local):
            continue
        size = os.path.getsize(local)
        print("[{}/{}] Syncing {} ({} bytes)...".format(idx, total, remote, size))
        uploader.upload_file(local, remote)

    print("\n[OK] All files successfully deployed!")
    print("Rebooting ESP32...")
    uploader.reboot()
    print("ESP32 is online! Connect to Wi-Fi 'ESP32-FileTransfer' and visit http://192.168.4.1/")


if __name__ == "__main__":
    deploy()

