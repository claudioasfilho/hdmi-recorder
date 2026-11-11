#!/usr/bin/env python3
import os
import re
import signal
import subprocess
import datetime
import psutil
import threading
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response

# --- Configuration ---
VIDEO_DEVICE = "/dev/video0"
AUDIO_DEVICE = "hw:3,0" 
VIDEO_CONTAINER = "mp4"
LOG_FILE = "/tmp/ffmpeg_recording.log"

app = Flask(__name__)

class RecorderState:
    def __init__(self):
        self.process = None
        self.current_filename = ""
        self.current_filepath = ""
        self.status = "IDLE"
        self.log_fd = None
        self.timer = None

recorder = RecorderState()

def sanitize_name(name):
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', name.strip())
    return cleaned or "capture"

def get_mounted_drives():
    drives = []
    excluded_fs = {'squashfs', 'tmpfs', 'devtmpfs', 'overlay', 'vfat_boot'}
    
    for part in psutil.disk_partitions(all=False):
        if part.fstype in excluded_fs or part.mountpoint in ['/', '/boot', '/boot/firmware']:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            free_gb = round(usage.free / (1024 ** 3), 1)
            drives.append({"mountpoint": part.mountpoint, "label": f"{part.mountpoint} - {free_gb}GB free"})
        except PermissionError:
            continue
    return drives

def stop_recording_logic():
    if recorder.process is None:
        return "NOT_RECORDING"

    # Cancel the timer if stop was triggered manually
    if recorder.timer is not None:
        recorder.timer.cancel()
        recorder.timer = None

    try:
        os.killpg(os.getpgid(recorder.process.pid), signal.SIGINT)
        # 120 SECOND TIMEOUT FIX: Prevents MP4 header corruption on large files
        recorder.process.wait(timeout=120)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(recorder.process.pid), signal.SIGKILL)
    except Exception:
        pass
    finally:
        recorder.process = None
        if recorder.log_fd:
            recorder.log_fd.close()
            recorder.log_fd = None

    os.sync()
    
    final_status = f"STOPPED: Saved {recorder.current_filename}"
    if os.path.exists(recorder.current_filepath):
        file_size_kb = os.path.getsize(recorder.current_filepath) / 1024
        if file_size_kb < 500:
            final_status = f"WARNING: {recorder.current_filename} is empty ({int(file_size_kb)} KB). HDCP blocking signal?"

    with open(LOG_FILE, 'a') as f:
        f.write(f"\n--- Recording gracefully stopped. {final_status} ---\n")

    recorder.status = final_status
    recorder.current_filename = ""
    recorder.current_filepath = ""
    
    return final_status

# --- Web UI ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HDMI Recorder</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; background-color: #f4f4f9; color: #333; margin: 0; }
        .container { max-width: 550px; margin: 20px auto; background: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 22px; margin-top: 0; text-align: center; }
        label { display: block; font-weight: 600; margin-top: 14px; margin-bottom: 6px; font-size: 14px; }
        select, input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 15px; }
        button { width: 100%; padding: 12px; font-size: 15px; font-weight: bold; border: none; border-radius: 6px; cursor: pointer; margin-top: 10px; color: white; }
        .btn-start { background-color: #28a745; margin-top: 18px; }
        .btn-stop { background-color: #dc3545; }
        .btn-refresh { background-color: #6c757d; padding: 8px; font-size: 13px; margin-top: 6px; }
        .btn-close-video { background-color: #6c757d; padding: 10px; margin-top: 10px; }
        .status-box { margin-top: 20px; padding: 12px; border-radius: 6px; background-color: #e9ecef; font-weight: 600; font-size: 14px; word-break: break-all; text-align: center;}
        
        .flex-row { display: flex; gap: 10px; }
        .flex-row input { width: 50%; }
        
        .file-list { margin-top: 20px; text-align: left; }
        .file-list h3 { font-size: 16px; margin-bottom: 10px; border-bottom: 2px solid #e9ecef; padding-bottom: 5px;}
        .file-list ul { list-style: none; padding: 0; margin: 0; max-height: 300px; overflow-y: auto; }
        .file-list li { background: #f8f9fa; padding: 10px; margin-bottom: 5px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; font-size: 13px; flex-wrap: wrap; gap: 8px;}
        
        .file-actions { display: flex; gap: 5px; flex-wrap: nowrap; }
        .file-actions a { text-decoration: none; font-weight: bold; padding: 6px 10px; border-radius: 4px; color: white; text-align: center; }
        .file-actions a:hover { opacity: 0.8; }
        .btn-play { background: #17a2b8; }
        .btn-download { background: #007bff; }
        .btn-rename { background: #ffc107; color: #333 !important; }
        .btn-delete { background: #dc3545; }

        .video-modal { display: none; margin-top: 20px; background: #000; padding: 10px; border-radius: 8px; text-align: center; }
        .video-modal h4 { color: white; margin: 0 0 10px 0; font-size: 14px; word-break: break-all; }
        
        .log-container { margin-top: 20px; background: #1e1e1e; color: #00ff00; padding: 10px; border-radius: 6px; height: 150px; overflow-y: auto; font-family: monospace; font-size: 11px; text-align: left; }
        .log-container pre { margin: 0; white-space: pre-wrap; word-wrap: break-word; }
        .log-title { font-size: 12px; color: #aaa; margin-bottom: 5px; margin-top: 20px; font-weight: bold; font-family: sans-serif; text-transform: uppercase; letter-spacing: 1px;}
    </style>
</head>
<body>
    <div class="container">
        <h1>HDMI Recorder</h1>
        
        <label for="driveSelect">1. Confirm Storage Drive:</label>
        <select id="driveSelect" onchange="fetchFiles()"></select>
        <button class="btn-refresh" onclick="loadDrives()">Rescan Drives</button>

        <label for="subfolder">2. Folder Name (Optional):</label>
        <input type="text" id="subfolder" placeholder="e.g. captures" onblur="fetchFiles()">

        <label for="recordName">3. Video Name:</label>
        <input type="text" id="recordName" placeholder="e.g. gameplay_1">

        <label>4. Auto-Stop Timer (Optional):</label>
        <div class="flex-row">
            <input type="number" id="timerMin" placeholder="Minutes" min="0">
            <input type="number" id="timerSec" placeholder="Seconds" min="0">
        </div>

        <button class="btn-start" onclick="startRecording()">Start Recording</button>
        <button class="btn-stop" onclick="stopRecording()">Stop Recording</button>
        
        <div class="status-box">
            Status: <span id="statusText">Checking...</span>
        </div>

        <div class="video-modal" id="videoModal">
            <h4 id="videoTitle">Video Title</h4>
            <video id="videoPlayer" width="100%" controls style="border-radius: 4px; background: black;">
                Your browser does not support the video tag.
            </video>
            <button class="btn-close-video" onclick="closeVideo()">Close Player</button>
        </div>

        <div class="file-list" id="fileListContainer">
            <h3>Saved Recordings</h3>
            <ul id="fileList"><li>No files found.</li></ul>
        </div>

        <div class="log-title">Live Diagnostics</div>
        <div class="log-container" id="logBox">
            <pre id="logText">Waiting for recording to start...</pre>
        </div>
    </div>

    <script>
        let lastStatus = "";

        async function loadDrives() {
            try {
                let res = await fetch('/drives');
                let drives = await res.json();
                let select = document.getElementById('driveSelect');
                select.innerHTML = '';
                
                if (drives.length === 0) {
                    let opt = document.createElement('option');
                    opt.value = '';
                    opt.innerText = 'No thumb drive detected';
                    select.appendChild(opt);
                } else {
                    drives.forEach(d => {
                        let opt = document.createElement('option');
                        opt.value = d.mountpoint;
                        opt.innerText = d.label;
                        select.appendChild(opt);
                    });
                }
                fetchFiles();
            } catch (e) { console.error(e); }
        }

        async function fetchFiles() {
            let drive = document.getElementById('driveSelect').value;
            let subfolder = document.getElementById('subfolder').value;
            if (!drive) return;

            try {
                let res = await fetch(`/files?drive=${encodeURIComponent(drive)}&subfolder=${encodeURIComponent(subfolder)}`);
                let files = await res.json();
                let list = document.getElementById('fileList');
                
                if (files.length === 0) {
                    list.innerHTML = '<li>No videos found in this folder.</li>';
                    return;
                }

                let html = '';
                files.forEach(f => {
                    let encName = encodeURIComponent(f.name);
                    let encDrive = encodeURIComponent(drive);
                    let encSub = encodeURIComponent(subfolder);
                    
                    html += `<li>
                                <div style="flex-grow: 1; word-break: break-all; min-width: 150px;">
                                    <strong>${f.name}</strong><br>
                                    <span style="color:#666;">${f.size} MB</span>
                                </div>
                                <div class="file-actions">
                                    <a href="#" class="btn-play" onclick="playVideo('${encDrive}', '${encSub}', '${encName}'); return false;">▶</a>
                                    <a href="/download?drive=${encDrive}&subfolder=${encSub}&file=${encName}" class="btn-download" download>⬇</a>
                                    <a href="#" class="btn-rename" onclick="renameFile('${encDrive}', '${encSub}', '${encName}'); return false;">✎</a>
                                    <a href="#" class="btn-delete" onclick="deleteFile('${encDrive}', '${encSub}', '${encName}'); return false;">✖</a>
                                </div>
                            </li>`;
                });
                list.innerHTML = html;
            } catch (e) { console.error(e); }
        }

        async function deleteFile(drive, subfolder, file) {
            let decodedFile = decodeURIComponent(file);
            if (!confirm(`Are you sure you want to permanently delete:\\n${decodedFile}?`)) return;

            await fetch('/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ drive: decodeURIComponent(drive), subfolder: decodeURIComponent(subfolder), file: decodedFile })
            });
            fetchFiles();
        }

        async function renameFile(drive, subfolder, oldFile) {
            let decodedOld = decodeURIComponent(oldFile);
            let cleanName = decodedOld.replace(/\.mp4$/i, '');
            let newName = prompt(`Enter new name for this video:`, cleanName);
            
            if (!newName || newName === cleanName) return;

            await fetch('/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    drive: decodeURIComponent(drive), 
                    subfolder: decodeURIComponent(subfolder), 
                    old_file: decodedOld, 
                    new_file: newName 
                })
            });
            fetchFiles();
        }

        function playVideo(drive, subfolder, file) {
            let url = `/play?drive=${drive}&subfolder=${subfolder}&file=${file}`;
            document.getElementById('videoTitle').innerText = decodeURIComponent(file);
            let player = document.getElementById('videoPlayer');
            player.src = url;
            document.getElementById('videoModal').style.display = 'block';
            player.play();
        }

        function closeVideo() {
            let player = document.getElementById('videoPlayer');
            player.pause();
            player.src = "";
            document.getElementById('videoModal').style.display = 'none';
        }

        async function fetchStatus() {
            try {
                let res = await fetch('/status');
                let data = await res.json();
                let statusEl = document.getElementById('statusText');
                statusEl.innerText = data.status;
                
                if (data.status.includes("WARNING") || data.status.includes("ERROR")) {
                    statusEl.style.color = "#dc3545";
                } else {
                    statusEl.style.color = "#333";
                }

                if (lastStatus && lastStatus.includes("RECORDING") && data.status.includes("STOPPED")) {
                    setTimeout(fetchFiles, 1000);
                }
                lastStatus = data.status;

            } catch (e) { document.getElementById('statusText').innerText = 'Connection Error'; }
        }

        async function fetchLog() {
            try {
                let res = await fetch('/log');
                let data = await res.json();
                let logElement = document.getElementById('logText');
                let logBox = document.getElementById('logBox');
                
                if (logElement.innerText !== data.log) {
                    logElement.innerText = data.log;
                    logBox.scrollTop = logBox.scrollHeight;
                }
            } catch (e) { }
        }

        async function startRecording() {
            let drive = document.getElementById('driveSelect').value;
            let subfolder = document.getElementById('subfolder').value;
            let name = document.getElementById('recordName').value;
            let timerMin = parseInt(document.getElementById('timerMin').value) || 0;
            let timerSec = parseInt(document.getElementById('timerSec').value) || 0;
            let duration = (timerMin * 60) + timerSec;

            if (!drive) {
                alert('Please connect a drive and select it first.');
                return;
            }

            await fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ drive: drive, subfolder: subfolder, name: name, duration: duration })
            });
            fetchStatus();
        }

        async function stopRecording() {
            await fetch('/stop', { method: 'POST' });
            fetchStatus();
            setTimeout(fetchFiles, 1000); 
        }

        loadDrives();
        setInterval(fetchStatus, 1500);
        setInterval(fetchLog, 1500);
    </script>
</body>
</html>
"""

# --- API Endpoints ---
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/drives', methods=['GET'])
def list_drives():
    return jsonify(get_mounted_drives())

@app.route('/files', methods=['GET'])
def list_files():
    base_mount = request.args.get('drive', '').strip()
    subfolder = request.args.get('subfolder', '').strip()
    
    if not base_mount or not os.path.ismount(base_mount):
        return jsonify([])
        
    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    if not os.path.exists(target_dir):
        return jsonify([])
        
    files = []
    try:
        for f in os.listdir(target_dir):
            if f.lower().endswith(f".{VIDEO_CONTAINER}"):
                path = os.path.join(target_dir, f)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                files.append({"name": f, "size": round(size_mb, 2)})
        
        files.sort(key=lambda x: x["name"], reverse=True)
    except Exception:
        pass
        
    return jsonify(files)

@app.route('/download', methods=['GET'])
def download_file():
    base_mount = request.args.get('drive', '').strip()
    subfolder = request.args.get('subfolder', '').strip()
    filename = request.args.get('file', '').strip()
    
    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    return send_from_directory(target_dir, filename, as_attachment=True)

@app.route('/play', methods=['GET'])
def play_file():
    base_mount = request.args.get('drive', '').strip()
    subfolder = request.args.get('subfolder', '').strip()
    filename = request.args.get('file', '').strip()
    
    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    filepath = os.path.join(target_dir, filename)
    
    if not os.path.exists(filepath):
        return "File not found", 404

    file_size = os.path.getsize(filepath)
    range_header = request.headers.get('Range', None)
    
    if not range_header:
        return send_from_directory(target_dir, filename)
        
    byte1, byte2 = 0, None
    m = re.search(r'(\d+)-(\d*)', range_header)
    if m:
        g = m.groups()
        if g[0]: byte1 = int(g[0])
        if g[1]: byte2 = int(g[1])

    if byte2 is None:
        byte2 = file_size - 1
        
    length = byte2 - byte1 + 1
    
    def generate():
        with open(filepath, 'rb') as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                chunk_size = min(remaining, 1024 * 1024)
                data = f.read(chunk_size)
                if not data: break
                remaining -= len(data)
                yield data

    rv = Response(generate(), 206, mimetype='video/mp4', direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    return rv

@app.route('/delete', methods=['POST'])
def delete_file():
    data = request.get_json() or {}
    base_mount = data.get("drive", "").strip()
    subfolder = data.get("subfolder", "").strip()
    filename = data.get("file", "").strip()
    
    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    filepath = os.path.join(target_dir, filename)
    
    if os.path.exists(filepath) and os.path.isfile(filepath):
        try:
            os.remove(filepath)
            return jsonify({"status": "SUCCESS"})
        except Exception as e:
            return jsonify({"status": f"ERROR: {str(e)}"})
    return jsonify({"status": "FILE_NOT_FOUND"})

@app.route('/rename', methods=['POST'])
def rename_file():
    data = request.get_json() or {}
    base_mount = data.get("drive", "").strip()
    subfolder = data.get("subfolder", "").strip()
    old_file = data.get("old_file", "").strip()
    new_file_raw = data.get("new_file", "").strip()
    
    clean_new_name = sanitize_name(new_file_raw.replace('.mp4', '').replace('.MP4', ''))
    new_file = f"{clean_new_name}.{VIDEO_CONTAINER}"

    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    old_filepath = os.path.join(target_dir, old_file)
    new_filepath = os.path.join(target_dir, new_file)
    
    if os.path.exists(old_filepath) and os.path.isfile(old_filepath):
        try:
            os.rename(old_filepath, new_filepath)
            return jsonify({"status": "SUCCESS"})
        except Exception as e:
            return jsonify({"status": f"ERROR: {str(e)}"})
    return jsonify({"status": "FILE_NOT_FOUND"})

@app.route('/status', methods=['GET'])
def get_status():
    if recorder.process is not None and recorder.process.poll() is not None:
        recorder.process = None
        recorder.status = "IDLE (Process ended unexpectedly)"
    return jsonify({"status": recorder.status})

@app.route('/log', methods=['GET'])
def get_log():
    try:
        if not os.path.exists(LOG_FILE):
            return jsonify({"log": "No logs generated yet. Press Start Recording."})
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            tail = "".join(lines[-30:])
            return jsonify({"log": tail})
    except Exception as e:
        return jsonify({"log": f"Error reading log file: {str(e)}"})

@app.route('/start', methods=['POST'])
def start():
    if recorder.process is not None:
        return jsonify({"status": "ALREADY_RECORDING"})

    data = request.get_json() or {}
    base_mount = data.get("drive", "").strip()
    subfolder = data.get("subfolder", "").strip()
    custom_title = data.get("name", "")
    duration_seconds = int(data.get("duration", 0))

    if not base_mount or not os.path.ismount(base_mount):
        recorder.status = f"ERROR: Invalid or unmounted drive '{base_mount}'"
        return jsonify({"status": recorder.status})

    target_dir = os.path.join(base_mount, subfolder) if subfolder else base_mount
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        recorder.status = f"ERROR: Failed to create folder ({str(e)})"
        return jsonify({"status": recorder.status})

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    title = sanitize_name(custom_title)
    filename = f"{timestamp}_{title}.{VIDEO_CONTAINER}"
    output_filepath = os.path.join(target_dir, filename)

    # UPDATED FFPEG COMMAND WITH LIVE A/V SYNC FILTER (-af aresample=async=1)
    cmd = [
        "ffmpeg", "-y",
        "-analyzeduration", "100M",
        "-probesize", "50M",
        "-thread_queue_size", "1024",
        "-f", "v4l2",
        "-input_format", "mjpeg",
        "-framerate", "30",
        "-video_size", "1920x1080",
        "-i", VIDEO_DEVICE,
        "-thread_queue_size", "1024",
        "-f", "alsa",
        "-i", AUDIO_DEVICE,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "44100",
        "-af", "aresample=async=1",  # <-- LOCKS AUDIO TO VIDEO TIMESTAMPS
        "-movflags", "+faststart",
        output_filepath
    ]

    try:
        with open(LOG_FILE, 'w') as f:
            f.write(f"--- Starting new capture: {filename} ---\n")
            if duration_seconds > 0:
                f.write(f"--- Auto-Stop Timer set for {duration_seconds} seconds ---\n")
            f.write(f"Command: {' '.join(cmd)}\n\n")

        recorder.log_fd = open(LOG_FILE, 'a')
        
        recorder.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=recorder.log_fd,
            preexec_fn=os.setsid
        )
        recorder.current_filename = filename
        recorder.current_filepath = output_filepath
        
        if duration_seconds > 0:
            recorder.timer = threading.Timer(duration_seconds, stop_recording_logic)
            recorder.timer.start()
            recorder.status = f"RECORDING -> {filename} (Auto-stops in {duration_seconds}s)"
        else:
            recorder.status = f"RECORDING -> {filename}"

    except Exception as e:
        recorder.status = f"ERROR: {str(e)}"

    return jsonify({"status": recorder.status})

@app.route('/stop', methods=['POST'])
def stop():
    status_msg = stop_recording_logic()
    return jsonify({"status": status_msg})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
