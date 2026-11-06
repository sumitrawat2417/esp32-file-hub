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
        self.ap_ssid = wifi_cfg.get("ap_ssid", "ESP32-FileHub").strip()
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

    def connect(self, interactive_prompt=True):
        """
        Orchestrates network connection.
        If configured, attempts to connect to saved network.
        If no network is saved, prompts user in terminal to choose operation mode.
        """
        if self.sta_ssid:
            print("[WiFi] Saved network found: '{}'".format(self.sta_ssid))
            if self._start_sta():
                return self._build_status()
            print("[WiFi] Could not connect to '{}'.".format(self.sta_ssid))

        # Main mode selection loop with Back support
        if interactive_prompt:
            while True:
                print("\n" + "-" * 52)
                print("Select Wi-Fi Operation Mode:")
                print("  [1] Connect to Mobile Hotspot / Wi-Fi (Stay on PC network)")
                print("  [2] Standalone Access Point (ESP32-FileHub AP)")
                print("-" * 52)
                try:
                    choice = input("Enter choice [1 or 2, default: 2]: ").strip()
                except Exception:
                    choice = "2"

                if choice == "1":
                    res = self.interactive_terminal_setup()
                    if res == "connected":
                        return self._build_status()
                    elif res == "back":
                        continue
                    elif res == "ap":
                        break
                else:
                    break

        self._start_ap()
        return self._build_status()

    def scan_networks(self):
        """Scan for nearby 2.4 GHz Wi-Fi networks. Returns sorted list of (ssid, rssi, is_secure)."""
        was_active = self.sta.active()
        if not was_active:
            self.sta.active(True)

        try:
            print("[WiFi] Scanning nearby Wi-Fi networks...")
            raw = self.sta.scan()
            seen = {}
            for item in raw:
                try:
                    ssid = item[0].decode("utf-8").strip()
                except Exception:
                    continue
                if not ssid:
                    continue
                rssi = item[3]
                is_secure = (item[4] != 0)
                if ssid not in seen or rssi > seen[ssid][0]:
                    seen[ssid] = (rssi, is_secure)

            results = [(ssid, seen[ssid][0], seen[ssid][1]) for ssid in seen]
            results.sort(key=lambda x: x[1], reverse=True)
            return results
        except Exception as e:
            print("[WiFi] Scan error: {}".format(e))
            return []
        finally:
            if not was_active and not self.sta.isconnected():
                self.sta.active(False)

    def interactive_terminal_setup(self):
        """
        Interactive terminal wizard to scan, select network, enter password, and save.
        Returns 'connected', 'back', or 'ap'.
        """
        networks = None

        while True:
            print("\n" + "=" * 52)
            print("       Interactive Wi-Fi / Hotspot Setup")
            print("=" * 52)

            if networks is None:
                networks = self.scan_networks()

            if not networks:
                print("[WiFi] No networks found during scan.")
                print("  [M] Enter SSID manually")
                print("  [R] Rescan networks")
                print("  [B] Back to mode selection")
                print("  [C] Cancel (continue to AP mode)")
                action = input("\nEnter choice [M, R, B, C]: ").strip().upper()
                if action == "R":
                    networks = None
                    continue
                elif action == "B":
                    return "back"
                elif action == "C":
                    return "ap"
                elif action == "M":
                    selected_ssid = input("Enter SSID: ").strip()
                    if not selected_ssid:
                        continue
                else:
                    continue
            else:
                print("\nAvailable 2.4 GHz Networks:")
                limit = min(len(networks), 10)
                for i in range(limit):
                    ssid, rssi, is_secure = networks[i]
                    sec_icon = "🔒" if is_secure else "  "
                    print("  [{:2d}] {:<24} ({} dBm) {}".format(i + 1, ssid, rssi, sec_icon))
                print("  [ R] Rescan networks")
                print("  [ M] Enter SSID manually")
                print("  [ B] Back to mode selection")
                print("  [ C] Cancel (continue to AP mode)")

                choice = input("\nSelect network [1-{}, R, M, B, C]: ".format(limit)).strip().upper()
                if choice == "B":
                    return "back"
                elif choice == "C":
                    return "ap"
                elif choice == "R":
                    networks = None
                    continue
                elif choice == "M":
                    selected_ssid = input("Enter SSID (or 'b' to go back): ").strip()
                    if not selected_ssid or selected_ssid.lower() == "b":
                        continue
                else:
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < limit:
                            selected_ssid = networks[idx][0]
                        else:
                            print("Invalid selection.")
                            continue
                    except ValueError:
                        print("Invalid selection.")
                        continue

            # Password entry and retry loop
            while True:
                password = input("\nEnter password for '{}' (or 'b' to go back): ".format(selected_ssid)).strip()
                if password.lower() in ("b", "back"):
                    break  # Return to network selection list

                print("\n[WiFi] Connecting to '{}'...".format(selected_ssid))
                self.sta_ssid = selected_ssid
                self.sta_password = password
                if self._start_sta():
                    try:
                        try:
                            from .config import ConfigManager
                        except (ImportError, ValueError):
                            try:
                                from esp32_file_hub.config import ConfigManager
                            except (ImportError, ValueError):
                                try:
                                    from esp32_transfer.config import ConfigManager
                                except (ImportError, ValueError):
                                    from config import ConfigManager

                        cfg = ConfigManager.load()
                        if "wifi" not in cfg:
                            cfg["wifi"] = {}
                        cfg["wifi"]["sta_ssid"] = selected_ssid
                        cfg["wifi"]["sta_password"] = password
                        ConfigManager.save(cfg)
                        print("[WiFi] Configuration persisted to 'config.json'!")
                    except Exception as e:
                        print("[WiFi] Warning: Could not save config: {}".format(e))
                    return "connected"
                else:
                    print("\n[WiFi] Connection failed to '{}'.".format(selected_ssid))
                    print("Options:")
                    print("  [1] Re-enter password for '{}'".format(selected_ssid))
                    print("  [2] Choose another network (Back)")
                    print("  [3] Fall back to Standalone AP mode")
                    fail_choice = input("Enter choice [1, 2, 3, default: 1]: ").strip()
                    if fail_choice == "2":
                        break  # Back to network list
                    elif fail_choice == "3":
                        self.sta_ssid = ""
                        self.sta_password = ""
                        return "ap"
                    else:
                        continue  # Re-enter password

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

