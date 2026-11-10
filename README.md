# Raspberry Pi Headless HDMI Recorder

A lightweight, headless HDMI recording appliance built for the Raspberry Pi 4. It captures 1080p video from a USB 3.0 capture card, encodes it with FFmpeg, and provides a web dashboard for remote management.

## Features
* **1080p Hardware Capture:** Utilizes the Pi 4's PCIe USB 3.0 controller for full-bandwidth recording without frame drops.
* **Web Dashboard:** Start, stop, download, play, rename, and delete recordings directly from a web browser.
* **Web-Optimized Streaming:** Encodes in H.264 `mp4` with the `+faststart` flag, allowing videos to play instantly in the browser without downloading the entire file first.
* **Isolated Environment:** Runs entirely within a Python virtual environment (`cfenv`) and operates as a background `systemd` service.

## Hardware Requirements
* Raspberry Pi 4 (Raspberry Pi OS 64-bit Bookworm required for USB 3.0 drivers)
* USB 3.0 HDMI Capture Card (e.g., MacroSilicon / FHD Capture)
* External USB Storage Drive (e.g., thumb drive for saving large video files)

## Dependencies
```bash
sudo apt update && sudo apt install -y ffmpeg v4l-utils python3-flask python3-psutil
