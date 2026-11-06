"""
Configuration Management Subsystem
Handles application settings, defaults, schema validation, and persistence.
"""

import json

DEFAULT_CONFIG_PATH = "esp32_file_hub/config.json"

DEFAULT_CONFIG = {
    "wifi": {
        "hostname": "esp32",
        "sta_ssid": "",
        "sta_password": "",
        "ap_ssid": "ESP32-FileHub",
        "ap_password": "",
        "connect_timeout_s": 15
    },
    "server": {
        "port": 80,
        "chunk_size": 1024,
        "static_dir": "esp32_file_hub/www"
    }
}


class ConfigManager:
    """Manages application configuration with validation and default fallback."""

    @staticmethod
    def _find_config_path(filepath=None):
        if filepath:
            return filepath
        candidates = [
            "esp32_file_hub/config.json",
            "/esp32_file_hub/config.json",
            "esp32_transfer/config.json",
            "/esp32_transfer/config.json",
            "config.json",
            "/config.json"
        ]
        for c in candidates:
            try:
                with open(c, "r"):
                    return c
            except Exception:
                pass
        return DEFAULT_CONFIG_PATH

    @staticmethod
    def load(filepath=None):
        """Load configuration from JSON file or return standard defaults."""
        target_path = ConfigManager._find_config_path(filepath)
        config = dict(DEFAULT_CONFIG)
        try:
            with open(target_path, "r") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    # Merge user settings into default schema
                    for section, values in user_data.items():
                        if section in config and isinstance(values, dict):
                            config[section].update(values)
                        else:
                            config[section] = values
            print("[Config] Configuration loaded from '{}'".format(target_path))
        except OSError:
            print("[Config] '{}' not found. Using defaults.".format(target_path))
            ConfigManager.save(config, target_path)
        except Exception as e:
            print("[Config] Warning: Failed to parse '{}' ({}). Using defaults.".format(target_path, e))

        return config

    @staticmethod
    def save(config, filepath=DEFAULT_CONFIG_PATH):
        """Persist configuration object to JSON file on flash."""
        try:
            with open(filepath, "w") as f:
                json.dump(config, f)
            print("[Config] Saved settings to '{}'".format(filepath))
            return True
        except Exception as e:
            print("[Config] Error writing '{}': {}".format(filepath, e))
            return False

