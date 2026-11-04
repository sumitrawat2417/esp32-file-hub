"""
WiFi Manager for ESP32 MicroPython
Handles Station (STA) connection with fallback to Access Point (AP) mode.
"""

import network
import time
import json

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "wifi": {
        "sta_ssid": "",
        "sta_password": "",
        "ap_ssid": "ESP32-FileTransfer",
        "ap_password": "",
        "connect_timeout_s": 15
    },
    "server": {
        "port": 80
    }
}


def load_config(filepath=CONFIG_FILE):
    """Load configuration from JSON file or return default configuration."""
    try:
        with open(filepath, "r") as f:
            config = json.load(f)
            print("[WiFi] Configuration loaded successfully.")
            return config
    except OSError:
        print("[WiFi] Configuration file not found. Using default settings.")
        return DEFAULT_CONFIG
    except Exception as e:
        print("[WiFi] Failed to parse config ({}). Using default settings.".format(e))
        return DEFAULT_CONFIG


def start_ap(ap_ssid, ap_password=""):
    """
    Initialize and activate Access Point (AP) mode.
    Creates a standalone Wi-Fi hotspot on the ESP32.
    """
    print("[WiFi] Starting Access Point mode...")
    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    # Configure AP authentication
    if ap_password and len(ap_password) >= 8:
        # WPA2-PSK (authmode 3)
        ap.config(essid=ap_ssid, password=ap_password, authmode=network.AUTH_WPA2_PSK)
        print("[WiFi] AP '{}' active with WPA2-PSK security.".format(ap_ssid))
    else:
        # Open network (authmode 0)
        ap.config(essid=ap_ssid, authmode=network.AUTH_OPEN)
        print("[WiFi] AP '{}' active as an open network.".format(ap_ssid))

    # Allow AP interface a brief moment to stabilize
    time.sleep(1)
    ifconfig = ap.ifconfig()
    print("[WiFi] AP IP Address: {}".format(ifconfig[0]))
    print("[WiFi] Subnet: {}, Gateway: {}".format(ifconfig[1], ifconfig[2]))

    return {"mode": "AP", "ip": ifconfig[0], "interface": ap, "ifconfig": ifconfig}


def connect_sta(ssid, password, timeout_s=15):
    """
    Attempt to connect to an existing Wi-Fi network in Station (STA) mode.
    Returns network info dict on success, or None on failure/timeout.
    """
    if not ssid:
        print("[WiFi] No Station (STA) SSID specified.")
        return None

    print("[WiFi] Connecting to Wi-Fi network '{}'...".format(ssid))
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.connect(ssid, password)

    start_time = time.time()
    while not sta.isconnected():
        elapsed = time.time() - start_time
        if elapsed > timeout_s:
            print("[WiFi] Connection to '{}' timed out after {}s.".format(ssid, timeout_s))
            sta.active(False)
            return None
        time.sleep(0.5)

    ifconfig = sta.ifconfig()
    print("[WiFi] Connected to '{}' successfully!".format(ssid))
    print("[WiFi] Assigned IP Address: {}".format(ifconfig[0]))
    print("[WiFi] Subnet: {}, Gateway: {}, DNS: {}".format(ifconfig[1], ifconfig[2], ifconfig[3]))

    return {"mode": "STA", "ip": ifconfig[0], "interface": sta, "ifconfig": ifconfig}


def setup_network(config=None):
    """
    Main entry point for network initialization.
    Tries STA mode first if credentials are configured;
    falls back to AP mode if connection fails or no credentials exist.
    """
    if config is None:
        config = load_config()

    wifi_cfg = config.get("wifi", {})
    sta_ssid = wifi_cfg.get("sta_ssid", "").strip()
    sta_password = wifi_cfg.get("sta_password", "")
    ap_ssid = wifi_cfg.get("ap_ssid", "ESP32-FileTransfer").strip()
    ap_password = wifi_cfg.get("ap_password", "")
    timeout = wifi_cfg.get("connect_timeout_s", 15)

    # 1. Try Station (STA) mode if SSID provided
    if sta_ssid:
        res = connect_sta(sta_ssid, sta_password, timeout_s=timeout)
        if res:
            return res
        print("[WiFi] Falling back to Access Point (AP) mode...")

    # 2. Fall back to Access Point (AP) mode
    return start_ap(ap_ssid, ap_password)


if __name__ == "__main__":
    print("=== ESP32 Wi-Fi Manager Self-Test ===")
    net_info = setup_network()
    print("=== Network Ready: Mode={} | IP={} ===".format(net_info["mode"], net_info["ip"]))

