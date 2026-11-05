"""
Application Main Entry Point
Boots up configuration, network controller, and starts the HTTP application server.
"""

import gc
from app.config import ConfigManager
from app.wifi import WiFiManager
from app.server import WebServer


def main():
    print("=" * 48)
    print("      ESP32 File Transfer Tool v1.0.0")
    print("=" * 48)

    # 1. Load application configuration
    config = ConfigManager.load()

    # 2. Establish wireless networking (STA with AP fallback)
    wifi = WiFiManager(config)
    net_status = wifi.connect()

    # 3. Launch HTTP web server
    server = WebServer(config, ip_address=net_status["ip"])
    server.start()


if __name__ == "__main__":
    gc.collect()
    try:
        main()
    except KeyboardInterrupt:
        print("\n[System] Shutdown requested by user.")
    except Exception as e:
        print("\n[System] Fatal crash: {}".format(e))

