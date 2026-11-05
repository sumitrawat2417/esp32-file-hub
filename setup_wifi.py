"""
Standalone Terminal Wi-Fi & Hotspot Setup Wizard for ESP32
Run this script in Thonny or serial terminal to scan nearby Wi-Fi networks,
choose your hotspot, enter the password, and save directly to config.json.
"""

from app.config import ConfigManager
from app.wifi import WiFiManager


def main():
    print("=" * 52)
    print("      ESP32 Wi-Fi & Hotspot Terminal Setup")
    print("=" * 52)
    config = ConfigManager.load()
    wifi = WiFiManager(config)
    res = wifi.interactive_terminal_setup()

    if res == "connected":
        print("\n[Done] You can now run 'esp32_transfer.py' to start the server.")
    else:
        print("\n[Done] Setup exited. Board will use default configuration.")


if __name__ == "__main__":
    main()

