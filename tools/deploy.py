"""
One-Click Deployment Tool for ESP32 File Hub
Automatically detects connected ESP32, syncs all project files and directories,
and soft-reboots the device in seconds using MicroPython Raw REPL.
Supports standalone executable builds (PyInstaller) and direct script execution.
"""

import os
import sys
import time
import json

def pause_if_interactive():
    """Wait for Enter key only when running in an interactive terminal without --no-pause."""
    if "--no-pause" not in sys.argv and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: 'pyserial' is required. Run: pip install pyserial")
    pause_if_interactive()
    sys.exit(1)


def get_base_dir():
    """Resolve project root directory for regular execution and PyInstaller bundles."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # If this script is in tools/, the project root is one level up
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, ".."))
    if os.path.exists(os.path.join(parent_dir, "esp32_file_hub")):
        return parent_dir
    if os.path.exists(os.path.join(parent_dir, "esp32_transfer")):
        return parent_dir
    return script_dir


def find_esp32_port():
    """Auto-detect USB serial port for ESP32."""
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").lower()
        if any(chip in desc for chip in ["cp210", "ch340", "ch9102", "ftdi", "usb to uart", "esp32"]):
            return p.device

    # Fallback to first available non-standard port
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
        self.ser.write(b"\r\x03\x03")
        time.sleep(0.2)
        self.ser.reset_input_buffer()

        self.ser.write(b"\x01")
        time.sleep(0.2)
        resp = self.ser.read_all()
        if b"raw REPL" not in resp:
            self.ser.write(b"\r\x03\x01")
            time.sleep(0.3)
            resp = self.ser.read_all()

    def execute(self, cmd_str):
        """Execute a Python command block in raw REPL."""
        cmd_bytes = cmd_str.encode("utf-8") + b"\x04"
        self.ser.write(cmd_bytes)

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
        """Recursively ensure a directory path exists on ESP32."""
        code = (
            "import os\n"
            "d = '{0}'\n"
            "parts = d.strip('/').split('/')\n"
            "curr = ''\n"
            "for p in parts:\n"
            "    curr = (curr + '/' + p) if curr else p\n"
            "    try:\n"
            "        os.mkdir(curr)\n"
            "    except:\n"
            "        pass\n"
        ).format(dir_path)
        self.execute(code)

    def remove_file(self, remote_path):
        """Remove file if it exists."""
        code = (
            "import os\n"
            "try:\n"
            "    os.remove('{0}')\n"
            "except:\n"
            "    pass\n"
        ).format(remote_path)
        self.execute(code)

    def remove_dir_recursive(self, remote_dir):
        """Recursively remove a directory and its contents on the board."""
        code = (
            "import os\n"
            "def _rm(d):\n"
            "    try:\n"
            "        for i in os.listdir(d):\n"
            "            p = d + '/' + i\n"
            "            try:\n"
            "                _rm(p)\n"
            "            except:\n"
            "                try: os.remove(p)\n"
            "                except: pass\n"
            "        os.rmdir(d)\n"
            "    except:\n"
            "        try: os.remove(d)\n"
            "        except: pass\n"
            "_rm('{0}')\n"
        ).format(remote_dir)
        self.execute(code)

    def get_remote_hashes(self, remote_paths):
        """Query SHA-256 hashes of remote files in a single fast Raw REPL batch call."""
        code = (
            "import os\n"
            "try:\n"
            "    import uhashlib as hashlib\n"
            "except:\n"
            "    import hashlib\n"
            "try:\n"
            "    import ubinascii as binascii\n"
            "except:\n"
            "    import binascii\n"
            "try:\n"
            "    import ujson as json\n"
            "except:\n"
            "    import json\n"
            "targets = {0}\n"
            "res = {{}}\n"
            "for p in targets:\n"
            "    try:\n"
            "        h = hashlib.sha256()\n"
            "        with open(p, 'rb') as f:\n"
            "            while True:\n"
            "                c = f.read(512)\n"
            "                if not c: break\n"
            "                h.update(c)\n"
            "        res[p] = binascii.hexlify(h.digest()).decode('utf-8')\n"
            "    except:\n"
            "        res[p] = None\n"
            "print('HASH_MAP:' + json.dumps(res))\n"
        ).format(repr(remote_paths))

        resp = self.execute(code).decode("utf-8", errors="ignore")
        for line in resp.splitlines():
            if "HASH_MAP:" in line:
                raw_json = line[line.find("HASH_MAP:") + len("HASH_MAP:"):].strip()
                try:
                    import json
                    return json.loads(raw_json)
                except Exception:
                    pass
        return {}

    def upload_file(self, local_path, remote_path):
        """Upload file content using raw REPL."""
        with open(local_path, "rb") as f:
            content = f.read()

        self.execute("f = open('{}', 'wb')".format(remote_path))

        chunk_size = 256
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            self.execute("f.write({})".format(repr(chunk)))

        self.execute("f.close()")

    def reboot(self):
        """Exit raw REPL and soft reboot."""
        if self.ser:
            self.ser.write(b"\x02")
            self.ser.close()


def compute_local_sha256(filepath):
    """Compute local file SHA-256 hex digest."""
    import hashlib
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def deploy():
    print("=" * 56)
    print("     ESP32 File Transfer Tool - Smart Installer")
    print("=" * 56)

    port = find_esp32_port()
    if not port:
        print("\n[!] No ESP32 detected.")
        print("    Please connect your ESP32 with a USB data cable and try again.")
        pause_if_interactive()
        return

    print("Found ESP32 on port: {}".format(port))
    uploader = RawReplUploader(port)

    print("Connecting to ESP32...")
    if not uploader.connect():
        pause_if_interactive()
        return

    base_dir = get_base_dir()

    # Prefer config.local.json (ignored by git) or config.json; fallback to config.example.json
    if os.path.exists(os.path.join(base_dir, "config.local.json")):
        config_source = "config.local.json"
    elif os.path.exists(os.path.join(base_dir, "config.json")):
        config_source = "config.json"
    else:
        config_source = "config.example.json"

    # Clean up all legacy files and folders from root so EVERYTHING is packed inside esp32_transfer/
    root_cleanup_files = [
        "file_manager.py",
        "web_server.py",
        "wifi_manager.py",
        "setup_wifi.py",
        "esp32_transfer.py",
        "config.json",
        "main.py",
    ]
    for obs in root_cleanup_files:
        uploader.remove_file(obs)

    # Clean up legacy folders if migrating to esp32_file_hub/
    uploader.remove_dir_recursive("esp32_transfer")
    uploader.remove_dir_recursive("lib")
    uploader.remove_dir_recursive("app")
    uploader.remove_dir_recursive("www")

    # Files to sync: 100% packed inside esp32_file_hub/
    pkg_config = os.path.join(base_dir, "esp32_file_hub", "config.json")
    if not os.path.exists(pkg_config):
        pkg_config = os.path.join(base_dir, config_source)

    files_to_sync = [
        (os.path.join("esp32_file_hub", "__init__.py"), "esp32_file_hub/__init__.py"),
        (os.path.join("esp32_file_hub", "app.py"), "esp32_file_hub/app.py"),
        (os.path.join("esp32_file_hub", "config.py"), "esp32_file_hub/config.py"),
        (pkg_config, "esp32_file_hub/config.json"),
        (os.path.join("esp32_file_hub", "wifi.py"), "esp32_file_hub/wifi.py"),
        (os.path.join("esp32_file_hub", "dns.py"), "esp32_file_hub/dns.py"),
        (os.path.join("esp32_file_hub", "storage.py"), "esp32_file_hub/storage.py"),
        (os.path.join("esp32_file_hub", "server.py"), "esp32_file_hub/server.py"),
        (os.path.join("esp32_file_hub", "setup_wifi.py"), "esp32_file_hub/setup_wifi.py"),
        (os.path.join("esp32_file_hub", "www", "index.html"), "esp32_file_hub/www/index.html"),
    ]

    dirs_to_create = ["esp32_file_hub", "esp32_file_hub/www"]
    for d in dirs_to_create:
        uploader.make_remote_dir(d)

    print("Checking board status (differential sync)...")
    remote_targets = [remote for (_, remote) in files_to_sync]
    remote_hashes = uploader.get_remote_hashes(remote_targets)

    total = len(files_to_sync)
    updated_count = 0
    skipped_count = 0

    for idx, (rel_local, remote) in enumerate(files_to_sync, start=1):
        local_full = os.path.join(base_dir, rel_local)
        if not os.path.exists(local_full):
            print("[!] Warning: Skipped '{}' (file not found)".format(rel_local))
            continue

        local_hash = compute_local_sha256(local_full)
        remote_hash = (remote_hashes.get(remote) or "").lower()

        # Safety: If board already has saved config.json on flash, don't overwrite saved Wi-Fi credentials
        if remote.endswith("config.json") and remote_hash:
            print("[{}/{}] Preserving existing board config: {} (skipped)".format(idx, total, remote))
            skipped_count += 1
            continue

        if remote_hash and local_hash == remote_hash:
            print("[{}/{}] Up-to-date: {} (identical, skipped)".format(idx, total, remote))
            skipped_count += 1
            continue

        size = os.path.getsize(local_full)
        action = "Updating" if remote_hash else "Writing"
        print("[{}/{}] {} {} ({} bytes)...".format(idx, total, action, remote, size))
        uploader.upload_file(local_full, remote)
        updated_count += 1

    print("\n" + "=" * 56)
    if updated_count == 0:
        print(" [OK] All files are already up-to-date! (0 flash writes)")
    else:
        print(" [OK] Sync complete! ({} updated, {} unchanged, flash wear minimized)".format(updated_count, skipped_count))
    print("=" * 56)
    print("Rebooting ESP32...")
    uploader.reboot()
    print("\nYour ESP32 is ready! All files are packed in 'esp32_file_hub/'.")
    print("1. From Terminal / REPL (1-line command):")
    print("   >>> import esp32_file_hub; esp32_file_hub.start()")
    print("2. From Thonny IDE:")
    print("   Open 'esp32_file_hub/app.py' and click Run (F5)!")
    print("3. In Web Browser:")
    print("   Open: http://esp32.local/ (or http://192.168.4.1/)")
    print("4. Configure Wi-Fi from REPL:")
    print("   >>> import esp32_file_hub; esp32_file_hub.setup_wifi()")
    print("   (or click '📶 Wi-Fi' in the web interface)")
    print("=" * 56)
    pause_if_interactive()


if __name__ == "__main__":
    deploy()
