# boot.py -- executed on ESP32 startup
import gc
import esp

# Disable vendor OS debug prints to keep serial clean
try:
    esp.osdebug(None)
except Exception:
    pass

# Run initial garbage collection
gc.collect()

