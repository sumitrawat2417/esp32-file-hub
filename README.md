# ESP32 File Transfer Tool (`esp32-transfer`)

A lightweight, production-grade, browser-based utility for managing and transferring files to and from an **ESP32** running **MicroPython** over local Wi-Fi.

---

## 📖 Overview

Developing on the ESP32 with MicroPython often requires frequently copying auxiliary assets: Python libraries, UI images, fonts, configuration files (JSON/CSV), and sensor logs.

Normally, copying these files requires tethering the board to a computer via USB and using desktop IDEs (like Thonny). **ESP32 File Transfer Tool** eliminates this friction by hosting an embedded web application directly on the ESP32. Connect to the board over Wi-Fi, open its web page in any browser, and transfer files effortlessly without USB cables or special desktop software.

---

## ✨ Key Features

- 🌐 **Modern Web Interface**: Responsive single-page application (SPA) with a sleek dark theme, breadcrumb navigation, and live flash storage gauges.
- ⚡ **1-Click Automated Installer**: Includes `deploy.py` to auto-detect your ESP32 on USB and flash all application files in 5 seconds.
- 📶 **Dual Wi-Fi Modes**:
  - **Access Point (AP) Mode**: Hosts its own Wi-Fi network (default IP: `192.168.4.1`, SSID: `ESP32-FileTransfer`) for standalone field use.
  - **Station (STA) Mode**: Connects to your existing local Wi-Fi network with automatic fallback to AP mode if connection times out.
- 📁 **Full Directory & File Management**:
  - Upload single or multiple files via file picker or drag-and-drop.
  - Interactive breadcrumbs (`Root (/) / lib / ...`) to navigate nested directory trees.
  - Create new folders on the ESP32 filesystem (`POST /api/mkdir`).
  - Streamed file downloads with attachment headers.
  - Safe deletion for files and empty directories.
- 🛡️ **Reliable & Memory-Safe (ESP32 RAM Aware)**:
  - **Chunked Streaming**: 1 KB buffered read/write cycles keep Python RAM usage flat.
  - **Atomic Upload Staging**: Incoming files stream into `.upload.tmp` and are verified before atomically replacing the destination.
  - **Storage Pre-Check**: Compares upload `Content-Length` against available flash space, rejecting oversized uploads before saving.
  - **Path Traversal Protection**: Sanitizes and blocks `../` path traversal attempts.

---

## 🏗️ Project Architecture

```text
esp32-transfer/
├── esp32_transfer/           # Self-contained application package
│   ├── __init__.py           # Package exports: start(), setup_wifi()
│   ├── app.py                # Standalone Thonny runner (Run with F5)
│   ├── config.py             # ConfigManager: schema validation & defaults
│   ├── config.json           # Wi-Fi & server settings (inside package)
│   ├── wifi.py               # WiFiManager: OOP network controller with AP failover
│   ├── dns.py                # DNSServer: captive portal & mDNS resolution
│   ├── storage.py            # StorageManager: atomic file I/O & size tracking
│   ├── server.py             # WebServer: non-blocking HTTP socket server & REST API
│   ├── setup_wifi.py         # Interactive terminal Wi-Fi setup wizard
│   └── www/                  # Embedded web frontend
│       └── index.html        # Production SPA (vanilla HTML/CSS/JS, zero external CDNs)
├── tools/                    # Desktop utilities & deployers
│   ├── deploy.py             # Automated uploader (auto-detects COM port)
│   └── build_installer.bat   # PyInstaller build recipe
├── install.bat               # 1-Click Windows desktop launcher
├── README.md                 # Public documentation
└── .gitignore                # Protects internal docs/, pycache, etc.
```

---

## 🚀 Quick Start Guide

### 1. Flash to ESP32 (1-Click Deployment)
Connect your ESP32 to your PC via USB:
- **On Windows**: Simply double-click **`install.bat`**!
- **Or via Terminal (Windows/Mac/Linux)**:
  ```bash
  python tools/deploy.py
  ```
*The installer automatically cleans all legacy files from root, packs everything inside `esp32_transfer/`, and soft-reboots the device.*

### 2. Run the Application
You have two effortless options:

- **Single-Line Terminal Command (Thonny REPL / Serial)**:
  ```python
  import esp32_transfer; esp32_transfer.start()
  ```
- **Or Click Run in Thonny**:
  Open **`esp32_transfer/app.py`** in Thonny and press **F5** (Run)!

### 3. Connect & Open the Web App
1. On your phone, tablet, or PC, connect to the Wi-Fi network:  
   **SSID:** `ESP32-FileTransfer` *(Open network by default)*  
   *(Or keep PC on your mobile hotspot if configured)*
2. Open your web browser and navigate to:  
   👉 **`http://esp32.local/`** (or **`http://192.168.4.1/`**)
3. Browse, upload, create folders, inspect file percentages, and download files directly!

### 4. Interactive Wi-Fi Setup
To connect your ESP32 to your home Wi-Fi or PC Hotspot:
- In the Web UI: Click **`📶 Wi-Fi`** at the top right, or
- In Terminal / REPL:
  ```python
  import esp32_transfer; esp32_transfer.setup_wifi()
  ```
2. Open your web browser and navigate to:  
   👉 **`http://192.168.4.1/`**
3. Browse, upload, create folders, and download files directly!

---

## ⚙️ Configuration (`config.json`)

```json
{
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
```
- Leave `sta_ssid` blank to always run in standalone **Access Point (AP)** mode.
- Enter your router's `sta_ssid` and `sta_password` to join an existing local network. If connection fails, the board automatically falls back to AP mode so you never get locked out.

---

## 🗺️ Project Status & Roadmap

- [x] **Phase 1: Connectivity & Foundation**
  - [x] AP & STA Wi-Fi initialization with auto-fallback.
  - [x] Configuration manager with default schema merging.
- [x] **Phase 2: Core Filesystem Engine**
  - [x] Chunked streaming download handler.
  - [x] Atomic upload staging with `.upload.tmp` verification.
  - [x] Traversal protection and recursive directory creation.
- [x] **Phase 3: Production Refactoring & Web UI**
  - [x] Decoupled single-page application (`www/index.html`).
  - [x] Breadcrumb navigation & multi-file drag-and-drop.
  - [x] 1-Click automated deployment tool (`deploy.py`).
- [x] **Phase 4: Autostart Integration**
  - [x] Standalone boot lifecycle (`boot.py` & `main.py`).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
