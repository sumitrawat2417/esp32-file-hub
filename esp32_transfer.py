"""
ESP32 File Hub - Compatibility Shim
Maintains 100% backward compatibility for existing code importing 'esp32_transfer'.
"""

try:
    import esp32_file_hub as _hub
    start = _hub.start
    run = getattr(_hub, 'run', _hub.start)
    setup_wifi = _hub.setup_wifi
    main = getattr(_hub, 'main', _hub.start)
except Exception:
    pass
