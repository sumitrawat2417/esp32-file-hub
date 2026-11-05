"""
ESP32 File Transfer Tool - MicroPython Library Package
Boots configuration, network, and HTTP server.

Quick start in terminal / REPL:
    import esp32_transfer
    esp32_transfer.start()

Interactive Wi-Fi setup in terminal / REPL:
    import esp32_transfer
    esp32_transfer.setup_wifi()
"""

import gc

try:
    from .config import ConfigManager
    from .wifi import WiFiManager
    from .server import WebServer
    from .setup_wifi import setup_wifi
except (ImportError, ValueError):
    try:
        from esp32_transfer.config import ConfigManager
        from esp32_transfer.wifi import WiFiManager
        from esp32_transfer.server import WebServer
        from esp32_transfer.setup_wifi import setup_wifi
    except (ImportError, ValueError):
        from config import ConfigManager
        from wifi import WiFiManager
        from server import WebServer
        from setup_wifi import setup_wifi


def start(config_path=None):
    """Start the file transfer server."""
    gc.collect()
    print("=" * 52)
    print("        ESP32 File Transfer Tool v1.0.0")
    print("=" * 52)

    # 1. Load application configuration
    config = ConfigManager.load(config_path) if config_path else ConfigManager.load()

    # 2. Establish wireless networking (STA with AP fallback)
    wifi = WiFiManager(config)
    net_status = wifi.connect()

    ip = net_status.get("ip", "0.0.0.0")
    hostname = net_status.get("hostname", "esp32")
    mode = net_status.get("mode", "AP")
    ssid = net_status.get("ssid", "ESP32-FileTransfer")

    print("\n" + "-" * 52)
    if mode == "STA":
        print("🟢 MODE: CONNECTED TO HOTSPOT / WI-FI (Client Mode)")
        print("   Connected SSID : {}".format(ssid))
        print("   Assigned IP    : {}".format(ip))
        print("   Web Address    : http://{}.local/ or http://{}/".format(hostname, ip))
        print("-" * 52)
        print("👉 USER INSTRUCTIONS:")
        print("   1. Keep your PC connected to your hotspot/Wi-Fi.")
        print("   2. Open your browser and visit: http://{}.local/ (or http://{}/)".format(hostname, ip))
        print("   3. To change Wi-Fi: Click '📶 Wi-Fi' in web UI")
        print("      or run: import esp32_transfer; esp32_transfer.setup_wifi()")
    else:
        print("📡 MODE: STANDALONE ACCESS POINT (Host Mode)")
        print("   Wi-Fi Name (SSID) : {}".format(ssid))
        print("   Board IP          : {}".format(ip))
        print("   Web Address       : http://{}/ or http://{}.local/".format(ip, hostname))
        print("-" * 52)
        print("👉 USER INSTRUCTIONS:")
        print("   1. Connect your PC / Phone Wi-Fi to: '{}'".format(ssid))
        print("   2. Open your browser and visit: http://{}/".format(ip))
        print("   3. To connect to your PC Hotspot / Wi-Fi:")
        print("      Click '📶 Wi-Fi' in web UI or run: import esp32_transfer; esp32_transfer.setup_wifi()")
    print("=" * 52 + "\n")

    # 3. Launch HTTP web server
    server = WebServer(
        config,
        ip_address=ip,
        hostname=hostname,
        wifi_status=net_status
    )
    server.start()


def run(config_path=None):
    """Alias for start()."""
    start(config_path)


# Backward compatibility aliases
main = start

if __name__ == "__main__":
    start()


