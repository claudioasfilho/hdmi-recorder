# Raspberry Pi HDMI Video & Audio Recorder

A lightweight, self-hosted web application built with Flask and FFmpeg designed for Raspberry Pi. It captures 1080p HDMI video and audio via a USB capture card, streams live diagnostics, supports automated recording timers, and features a responsive web dashboard for managing, playing, and downloading your files directly from external storage.

---

## Features

- **Web-Based Dashboard:** Start, stop, and monitor recordings remotely from any browser on your local network.
- **Robust Process Management:** Includes a safety-timeout mechanism to ensure massive MP4 files properly write their index headers (`+faststart`) without corruption.
- **Live A/V Synchronization:** Utilizes real-time resampling filters (`-af aresample=async=1`) to prevent audio and video drift during long recording sessions.
- **Auto-Stop Timers:** Schedule unattended recordings down to the minute and second.
- **Direct Storage Integration:** Automatically detects and writes files to external USB drives/SSDs.
- **In-Browser Playback & Management:** Stream captured episodes instantly with chunked byte-range support, or rename, download, and delete files with a single click.

---

## Hardware Requirements

1. **Raspberry Pi 4 / 5** (running Raspberry Pi OS / Debian-based OS).
2. **USB HDMI Video Capture Card** (standard UVC/MJPEG-compatible capture dongle).
3. **External USB Drive or SSD** mounted for media storage (default path: `/media/pi/TESLADRIVE`).

---

## Software Prerequisites

Ensure your system has Python 3, `ffmpeg`, and build dependencies installed:

```bash
sudo apt update
sudo apt install -y python3-pip python3-flask python3-psutil ffmpeg
