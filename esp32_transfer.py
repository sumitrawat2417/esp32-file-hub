"""
ESP32 File Transfer Tool - Main Application Entrypoint
Boots up configuration, network controller, and starts the HTTP application server.
Run this file directly in Thonny or via terminal.
"""

import gc
from app.config import ConfigManager
from app.wifi import WiFiManager
from app.server import WebServer


def main():
    print("=" * 52)
    print("        ESP32 File Transfer Tool v1.0.0")
    print("=" * 52)

    # 1. Load application configuration
    config = ConfigManager.load()

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
        print("   2. Open your browser and visit: http://{}.local/".format(hostname))
        print("      (or http://{}/)".format(ip))
        print("   3. To return to Standalone AP mode, click '📶 Wi-Fi'")
        print("      in the web UI or clear 'sta_ssid' in config.json.")
    else:
        print("📡 MODE: STANDALONE ACCESS POINT (Host Mode)")
        print("   Wi-Fi Name (SSID) : {}".format(ssid))
        print("   Board IP          : {}".format(ip))
        print("   Web Address       : http://{}/ or http://{}.local/".format(ip, hostname))
        print("-" * 52)
        print("👉 USER INSTRUCTIONS:")
        print("   1. Connect your PC / Phone Wi-Fi to: '{}'".format(ssid))
        print("   2. Open your browser and visit: http://{}/".format(ip))
        print("   3. To avoid disconnecting your PC in the future:")
        print("      Click '📶 Wi-Fi' in the web interface to connect")
        print("      the ESP32 to your PC Hotspot / home Wi-Fi!")
    print("=" * 52 + "\n")

    # 3. Launch HTTP web server
    server = WebServer(
        config,
        ip_address=ip,
        hostname=hostname,
        wifi_status=net_status
    )
    server.start()


if __name__ == "__main__":
    gc.collect()
    try:
        main()
    except KeyboardInterrupt:
        print("\n[System] Shutdown requested by user.")
    except Exception as e:
        print("\n[System] Fatal crash: {}".format(e))

