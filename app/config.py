"""
Configuration Management Subsystem
Handles application settings, defaults, schema validation, and persistence.
"""

import json

DEFAULT_CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "wifi": {
        "sta_ssid": "",
        "sta_password": "",
        "ap_ssid": "ESP32-FileTransfer",
        "ap_password": "",
        "connect_timeout_s": 15
    },
    "server": {
        "port": 80,
        "chunk_size": 1024,
        "static_dir": "www"
    }
}


class ConfigManager:
    """Manages application configuration with validation and default fallback."""

    @staticmethod
    def load(filepath=DEFAULT_CONFIG_PATH):
        """Load configuration from JSON file or return standard defaults."""
        config = dict(DEFAULT_CONFIG)
        try:
            with open(filepath, "r") as f:
                user_data = json.load(f)
                if isinstance(user_data, dict):
                    # Merge user settings into default schema
                    for section, values in user_data.items():
                        if section in config and isinstance(values, dict):
                            config[section].update(values)
                        else:
                            config[section] = values
            print("[Config] Configuration loaded from '{}'".format(filepath))
        except OSError:
            print("[Config] '{}' not found. Using defaults.".format(filepath))
            ConfigManager.save(config, filepath)
        except Exception as e:
            print("[Config] Warning: Failed to parse '{}' ({}). Using defaults.".format(filepath, e))

        return config

    @staticmethod
    def save(config, filepath=DEFAULT_CONFIG_PATH):
        """Persist configuration dictionary to disk."""
        try:
            with open(filepath, "w") as f:
                json.dump(config, f)
            print("[Config] Configuration persisted to '{}'".format(filepath))
            return True
        except Exception as e:
            print("[Config] Error: Failed to save config: {}".format(e))
            return False

