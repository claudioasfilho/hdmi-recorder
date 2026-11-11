# Raspberry Pi HDMI Video & Audio Recorder

A lightweight, self-hosted web application built with Flask and FFmpeg for Raspberry Pi. It captures 1080p HDMI video and audio via a USB capture card, features real-time A/V synchronization, handles robust file finalization, supports automated recording timers, and provides a responsive web dashboard for managing, playing, and downloading your files directly from external storage.

---

## Features

- **Web-Based Dashboard:** Start, stop, and monitor recordings remotely from any browser on your local network.
- **Header Corruption Protection:** Incorporates a 120-second safety timeout mechanism to ensure massive MP4 files properly write their index headers (`+faststart`) without crashing or corrupting.
- **Live A/V Synchronization:** Utilizes real-time resampling filters (`-af aresample=async=1`) to eliminate clock drift and keep audio locked to video timestamps over long recording sessions.
- **Auto-Stop Timers:** Schedule unattended recordings down to the minute and second.
- **Direct Storage Integration:** Automatically detects, mounts, and writes files to external USB drives/SSDs.
- **In-Browser Playback & Management:** Stream captured episodes instantly with chunked byte-range support, or rename, download, and delete files with a single click.

---

## Hardware Requirements

1. **Raspberry Pi 4 / 5** (running Raspberry Pi OS / Debian-based OS).
2. **USB HDMI Video Capture Card** (standard UVC/MJPEG-compatible capture dongle).
3. **External USB Drive or SSD** mounted for media storage (default path: `/media/pi/TESLADRIVE`).

---

## Software Prerequisites

Ensure your system has Python 3, Flask, Psutil, and FFmpeg installed:

```bash
sudo apt update
sudo apt install -y python3-pip python3-flask python3-psutil ffmpeg
```

---

## Git Setup & Passwordless SSH

To avoid typing your credentials every time you push updates to GitHub, ensure your remote URL uses SSH:

```bash
cd /home/pi/webapp
git remote set-url origin git@github.com:claudioasfilho/hdmi-recorder.git
```

---

## Configuration

Open `app.py` to verify your video, audio input devices, and default storage mount point match your hardware:

```python
VIDEO_DEVICE = "/dev/video0"
AUDIO_DEVICE = "hw:3,0" 
BASE_DIR = "/media/pi/TESLADRIVE"
```

---

## Launching the Web App

### 1. Manual Launch (Testing)
To test the application interactively in your terminal:

```bash
python3 app.py
```

Open any browser on your network and navigate to `http://<your-raspberry-pi-ip>:5000`.

### 2. Using the Helper Startup Script (`start.sh`)
For a clean entry point that manages execution:

1. Create `start.sh` in your project root:
   ```bash
   nano start.sh
   ```
2. Paste the following script:
   ```bash
   #!/bin/bash
   cd "$(dirname "$0")"

   echo "Starting HDMI Recorder Web App..."
   exec python3 app.py
   ```
3. Make the script executable:
   ```bash
   chmod +x start.sh
   ```
4. Launch it anytime using:
   ```bash
   ./start.sh
   ```

---

## Setting Up Automatic Startup on Boot (Systemd)

To ensure the web app launches automatically every time your Raspberry Pi powers on or reboots, configure it as a systemd background service.

1. Create the service configuration file:
   ```bash
   sudo nano /etc/systemd/system/hdmirecorder.service
   ```
2. Paste the following configuration structure:
   ```ini
   [Unit]
   Description=HDMI Recorder Web App
   After=network.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/webapp
   ExecStart=/home/pi/webapp/start.sh
   Restart=always
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable hdmirecorder.service
   sudo systemctl start hdmirecorder.service
   ```

### Useful Service Management Commands

- **Check Status:** `sudo systemctl status hdmirecorder.service`
- **View Live Logs:** `sudo journalctl -u hdmirecorder.service -f`
- **Restart Service:** `sudo systemctl restart hdmirecorder.service`
- **Stop Service:** `sudo systemctl stop hdmirecorder.service`

---

## How to Use the Web Dashboard

1. **Confirm Storage Drive:** Select your mounted USB drive from the dropdown menu (click *Rescan Drives* if needed).
2. **Folder Name (Optional):** Type a subfolder name (e.g., `Spike`) to organize your captures.
3. **Video Name:** Enter a custom title for your recording (special characters are automatically cleaned up).
4. **Auto-Stop Timer (Optional):** Input minutes and/or seconds if you want the recording to automatically terminate after a set duration.
5. **Start / Stop:** Click **Start Recording** to begin. Live diagnostics stream in the console box below. When finished, click **Stop Recording** and wait briefly for the file header to safely finalize.
6. **Manage Recordings:** Use the action buttons next to each file to **Play** instantly in your browser, **Download** locally, **Rename**, or **Delete**.
