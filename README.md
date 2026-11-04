# ESP32 File Transfer Tool (`esp32-transfer`)

A lightweight, browser-based utility for managing and transferring files between a computer or mobile device and an **ESP32** running **MicroPython** over local Wi-Fi.

---

## 📖 Overview

When developing on the ESP32 with MicroPython, projects often require auxiliary assets: Python libraries, UI images, fonts, configuration files (JSON/CSV/text), and sensor data logs. 

Normally, copying these files requires tethering the board to a computer via USB and using desktop IDEs (like Thonny). **ESP32 File Transfer Tool** simplifies routine file transfers by hosting a lightweight local web interface directly on the ESP32. Simply connect to the board over Wi-Fi, open its web page in any browser, and transfer files effortlessly without USB cables or third-party desktop tools.

---

## ✨ Key Features (Planned MVP)

- 🌐 **Browser-Based Interface**: Transfer files through a responsive web UI accessible from PCs, laptops, smartphones, and tablets.
- 📶 **Dual Wi-Fi Modes**:
  - **Access Point (AP) Mode**: The ESP32 hosts its own Wi-Fi network (default IP: `192.168.4.1`) for direct connection in the field without an external router.
  - **Station (STA) Mode**: The ESP32 joins an existing local Wi-Fi network alongside your workstation.
- ⚡ **Local & Offline**: 100% self-hosted on the ESP32. Operates completely without internet access or cloud services.
- 📁 **File & Directory Management**:
  - Upload single and multiple files via file picker or drag-and-drop.
  - Upload entire directories while preserving folder structure.
  - Browse ESP32 directories and download files back to your device.
  - Inspect available filesystem storage space.
- 🛡️ **Reliable & Resource-Conscious**:
  - **Chunked streaming**: Data is read/written in small chunks to avoid exhausting ESP32 RAM.
  - **Safe uploads**: Staged using temporary files to prevent corrupted or partial file writes on interrupted connections.
  - **Path validation**: Built-in directory traversal and path sanitization protection.
  - **Overwrite safeguards**: Conflict notification before replacing existing files.

---

## 🛠️ Architecture & How It Works

```text
┌─────────────────────────┐                   ┌───────────────────────────────┐
│     Client Device       │                   │       ESP32 (MicroPython)     │
│ (PC / Mobile / Tablet)  │   HTTP over Wi-Fi │                               │
│                         │ ────────────────> │ ┌───────────────────────────┐ │
│  - Web Browser UI       │ <──────────────── │ │ Embedded HTTP Server      │ │
│  - Drag & Drop Uploads  │                   │ └─────────────┬─────────────┘ │
│  - File Download        │                   │               │               │
└─────────────────────────┘                   │ ┌─────────────▼─────────────┐ │
                                              │ │ MicroPython Filesystem    │ │
                                              │ │ (/lib, /assets, /data...) │ │
                                              │ └───────────────────────────┘ │
                                              └───────────────────────────────┘
```

1. **Wi-Fi Manager**: Initializes either AP mode or connects to an existing STA network.
2. **Embedded Web Server**: Serves HTML/JS/CSS assets and exposes REST endpoints for file listing, uploads, and downloads.
3. **Storage Controller**: Streams file chunks safely to and from the internal flash filesystem (LittleFS / FAT).

---

## 🎯 Target Hardware & Requirements

- **Microcontroller**: Standard ESP32 development board (e.g., ESP32 DevKit v1 / NodeMCU-32S).
- **Firmware**: MicroPython (latest stable release).
- **Client**: Any modern web browser (Chrome, Firefox, Safari, Edge) on desktop or mobile.
- **Initial Setup**: USB data cable and a serial tool (e.g., Thonny, `mpremote`, or `ampy`) are needed only for the one-time initial flashing and script deployment.

---

## 🗺️ Project Roadmap

- [ ] **Phase 1: Connectivity & Server Foundation**
  - [ ] AP & STA Wi-Fi initialization and configuration module.
  - [ ] Lightweight asynchronous/socket-based HTTP server.
- [ ] **Phase 2: Core Transfer Engine**
  - [ ] Chunked file upload handler with temporary file staging.
  - [ ] Streaming file download handler.
  - [ ] Filesystem query and path validation utility.
- [ ] **Phase 3: Web User Interface**
  - [ ] Compact, zero-dependency HTML/CSS/JS frontend served from the ESP32.
  - [ ] File selection, drag-and-drop, and upload progress feedback.
  - [ ] Directory navigation and storage gauge display.
- [ ] **Phase 4: Reliability & Edge Cases**
  - [ ] Testing memory pressure, large transfers, and network interruptions.
  - [ ] Mobile browser optimization.
- [ ] **Phase 5: Documentation & Release**
  - [ ] Installation guide, configuration examples, and verified hardware list.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
