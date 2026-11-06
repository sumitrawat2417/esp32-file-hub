"""
Interactive Wi-Fi Setup Wizard for ESP32
"""

try:
    from .config import ConfigManager
    from .wifi import WiFiManager
except (ImportError, ValueError):
    try:
        from esp32_file_hub.config import ConfigManager
        from esp32_file_hub.wifi import WiFiManager
    except (ImportError, ValueError):
        try:
            from esp32_transfer.config import ConfigManager
            from esp32_transfer.wifi import WiFiManager
        except (ImportError, ValueError):
            from config import ConfigManager
            from wifi import WiFiManager


def setup_wifi():
    """Run terminal interactive Wi-Fi setup."""
    print("=" * 52)
    print("      ESP32 Wi-Fi & Hotspot Terminal Setup")
    print("=" * 52)
    config = ConfigManager.load()
    wifi = WiFiManager(config)
    res = wifi.interactive_terminal_setup()

    if res == "connected":
        print("\n[Done] You can now start the server: import esp32_file_hub; esp32_file_hub.start()")
    else:
        print("\n[Done] Setup exited. Board will use default configuration.")
    return res


# Backward compatibility aliases
run_wizard = setup_wifi
main = setup_wifi

if __name__ == "__main__":
    setup_wifi()

