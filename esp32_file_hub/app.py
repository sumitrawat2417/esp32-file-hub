"""
ESP32 File Hub - App Runner
Run this file directly in Thonny or import from REPL:
    import esp32_file_hub; esp32_file_hub.start()
"""

try:
    import esp32_file_hub
    _pkg = esp32_file_hub
except ImportError:
    try:
        import esp32_transfer
        _pkg = esp32_transfer
    except ImportError:
        import __init__ as _pkg

if __name__ == "__main__":
    _pkg.start()

