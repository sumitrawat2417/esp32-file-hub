"""
WiFi Management Subsystem
Handles Station (STA) client and Access Point (AP) lifecycle with graceful failover.
"""

import network
import time


class WiFiManager:
    """Manages wireless interfaces, connectivity state, and fallback mechanisms."""

    def __init__(self, config):
        wifi_cfg = config.get("wifi", {})
        self.hostname = wifi_cfg.get("hostname", "esp32").strip() or "esp32"
        self.sta_ssid = wifi_cfg.get("sta_ssid", "").strip()
        self.sta_password = wifi_cfg.get("sta_password", "")
        self.ap_ssid = wifi_cfg.get("ap_ssid", "ESP32-FileTransfer").strip()
        self.ap_password = wifi_cfg.get("ap_password", "")
        self.timeout_s = wifi_cfg.get("connect_timeout_s", 15)

        # Set network hostname and mDNS broadcast before activating interfaces
        self._configure_hostname(self.hostname)

        self.sta = network.WLAN(network.STA_IF)
        self.ap = network.WLAN(network.AP_IF)
        self.active_mode = None
        self.ip_address = "0.0.0.0"

    def _configure_hostname(self, name):
        """Configure global hostname and mDNS broadcast before interface activation."""
        try:
            network.hostname(name)
            print("[WiFi] Hostname set to '{}' (accessible at http://{}.local/)".format(name, name))
        except (AttributeError, TypeError) as e:
            print("[WiFi] Note: network.hostname() not supported on this firmware build ({})".format(e))

    def connect(self):
        """
        Orchestrates network connection.
        Attempts STA mode if configured; falls back to standalone AP on failure.
        """
        if self.sta_ssid:
            if self._start_sta():
                return self._build_status()
            print("[WiFi] Falling back to Access Point mode...")

        self._start_ap()
        return self._build_status()

    def _start_sta(self):
        """Connect to an existing Wi-Fi network."""
        print("[WiFi] Connecting to Station network '{}'...".format(self.sta_ssid))
        self.sta.active(True)
        self.sta.connect(self.sta_ssid, self.sta_password)

        start = time.time()
        while not self.sta.isconnected():
            if (time.time() - start) > self.timeout_s:
                print("[WiFi] Connection to '{}' timed out.".format(self.sta_ssid))
                self.sta.active(False)
                return False
            time.sleep(0.5)

        ifcfg = self.sta.ifconfig()
        self.active_mode = "STA"
        self.ip_address = ifcfg[0]
        print("[WiFi] Connected successfully. IP: {}".format(self.ip_address))
        return True

    def _start_ap(self):
        """Initialize standalone Access Point hotspot."""
        print("[WiFi] Initializing Access Point '{}'...".format(self.ap_ssid))
        self.ap.active(True)

        if self.ap_password and len(self.ap_password) >= 8:
            self.ap.config(essid=self.ap_ssid, password=self.ap_password, authmode=network.AUTH_WPA2_PSK)
            print("[WiFi] AP active with WPA2-PSK security.")
        else:
            self.ap.config(essid=self.ap_ssid, authmode=network.AUTH_OPEN)
            print("[WiFi] AP active as an open network.")

        time.sleep(0.5)
        ifcfg = self.ap.ifconfig()
        self.active_mode = "AP"
        self.ip_address = ifcfg[0]
        print("[WiFi] AP ready. Gateway IP: {}".format(self.ip_address))
        return True

    def _build_status(self):
        """Return standardized network state dictionary."""
        return {
            "mode": self.active_mode,
            "ip": self.ip_address,
            "hostname": self.hostname,
            "mdns_url": "http://{}.local/".format(self.hostname),
            "ssid": self.sta_ssid if self.active_mode == "STA" else self.ap_ssid
        }

    def disconnect(self):
        """Deactivate all wireless interfaces."""
        if self.sta.active():
            self.sta.active(False)
        if self.ap.active():
            self.ap.active(False)
        self.active_mode = None
        print("[WiFi] Interfaces disabled.")

