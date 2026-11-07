import os
import sys
import io
import time
import asyncio
import uuid
import json
import socket
import subprocess
import urllib.parse
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Optional

try:
    import qrcode
    from qrcode.image.pil import PilImage
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]"])
    import qrcode
    from qrcode.image.pil import PilImage

try:
    import multipart
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-multipart"])
    import multipart

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.logger.logger import logger

PORT = 8090
devices = {}
device_meta = {}
ui_clients = []
pending_requests = {}
pending_device_map = {}
registered_files = {}
FILE_REGISTRY_TTL = 3600

STATE_FILE = os.path.join(PROJECT_ROOT, "Data", "SessionCookies", "connected_devices.json")
USER_HOME = os.path.expanduser("~")
PC_SHARE_DIR = os.path.join(USER_HOME, "Documents", "Jarvis", "JarvisShare")
os.makedirs(PC_SHARE_DIR, exist_ok=True)

STAGING_DIR = os.path.join(PROJECT_ROOT, "Data", "Staging")
os.makedirs(STAGING_DIR, exist_ok=True)


def get_local_ip():
    probe_targets = [
        ("8.8.8.8", 80),
        ("1.1.1.1", 80),
        ("192.168.43.1", 80),
        ("192.168.137.1", 80),
        ("192.168.1.1", 80),
        ("192.168.0.1", 80),
    ]
    for host, port in probe_targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.8)
            s.connect((host, port))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
        except Exception:
            pass

    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        preferred = []
        fallback = []
        for ip in ips:
            if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if ip.startswith("192.168.56.") or ip.startswith("172."):
                fallback.append(ip)
            elif ip.startswith("192.168.") or ip.startswith("10."):
                preferred.append(ip)
            else:
                fallback.append(ip)
        if preferred:
            return preferred[0]
        if fallback:
            return fallback[0]
    except Exception:
        pass

    return "127.0.0.1"


def update_state_file():
    try:
        state_dir = os.path.dirname(STATE_FILE)
        os.makedirs(state_dir, exist_ok=True)
        temp_file = f"{STATE_FILE}.{uuid.uuid4().hex}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(list(devices.keys()), f)
        os.replace(temp_file, STATE_FILE)
    except Exception as e:
        logger.error(f"Mobile Bridge: Failed to update state file -> {e}")


def fail_pending_requests_for_device(device_id: str, reason: str = "Device disconnected"):
    stale_ids = [req_id for req_id, dev_id in list(pending_device_map.items()) if dev_id == device_id]
    for req_id in stale_ids:
        pending_device_map.pop(req_id, None)
        fut = pending_requests.pop(req_id, None)
        if fut is not None and not fut.done():
            fut.set_result({"error": f"{reason} ({device_id})", "returncode": -1})


def get_pc_clipboard_text() -> str:
    if sys.platform == "win32":
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
                timeout=5,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            return out.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception:
            pass
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        except Exception:
            text = ""
        root.destroy()
        return text
    except Exception:
        return ""


def set_pc_clipboard_text(text: str) -> bool:
    if sys.platform == "win32":
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            proc.communicate(input=text.encode("utf-16le"), timeout=5)
            return proc.returncode == 0
        except Exception:
            pass
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    update_state_file()
    logger.info(f"Mobile Bridge Service Started on port {PORT}. Connected devices: {list(devices.keys())}")
    try:
        yield
    finally:
        for dev_id in list(devices.keys()):
            fail_pending_requests_for_device(dev_id, "Server shutting down")
        devices.clear()
        device_meta.clear()
        update_state_file()


app = FastAPI(title="Jarvis Mobile Bridge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


class CommandRequest(BaseModel):
    target_device: str
    command: str
    timeout: Optional[float] = 90.0


class RegisterFilesRequest(BaseModel):
    file_paths: List[str]


class TransferRequest(BaseModel):
    direction: str
    device_id: Optional[str] = None
    file_paths: List[str]


class QuickActionRequest(BaseModel):
    action: str
    payload: Optional[str] = None


def serialize_devices():
    out = []
    for did in list(devices.keys()):
        meta = device_meta.get(did, {})
        out.append({
            "id": did,
            "battery": meta.get("battery"),
            "storage": meta.get("storage"),
            "network": meta.get("network"),
        })
    return out


async def broadcast_ui(message: dict):
    dead = []
    for c in list(ui_clients):
        try:
            await c.send_json(message)
        except Exception:
            dead.append(c)
    for c in dead:
        if c in ui_clients:
            ui_clients.remove(c)


def cleanup_registered_files():
    now = time.time()
    expired = [
        token for token, info in list(registered_files.items())
        if now - info.get("created_at", 0) > FILE_REGISTRY_TTL
    ]
    for token in expired:
        info = registered_files.pop(token, None)
        if info:
            path = info.get("path", "")
            if path.startswith(STAGING_DIR) and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


def resolve_unique_save_path(directory: str, filename: str) -> str:
    safe_name = os.path.basename(filename.strip()) or f"file_{int(time.time())}"
    candidate = os.path.join(directory, safe_name)
    if not os.path.exists(candidate):
        return candidate
    name, ext = os.path.splitext(safe_name)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{name}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


async def send_device_request(device_id: str, payload: dict, timeout: float = 90.0):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' offline.")
    ws = devices[device_id]
    req_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    pending_requests[req_id] = future
    pending_device_map[req_id] = device_id
    payload["req_id"] = req_id

    try:
        await ws.send_json(payload)
    except Exception as e:
        pending_requests.pop(req_id, None)
        pending_device_map.pop(req_id, None)
        if not future.done():
            future.cancel()
        raise HTTPException(status_code=500, detail=f"Failed to send payload to device: {e}")

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        if not future.done():
            future.cancel()
        return {"error": f"Timeout: Device did not respond in {int(timeout)} seconds.", "returncode": -1}
    finally:
        pending_requests.pop(req_id, None)
        pending_device_map.pop(req_id, None)


@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "port": PORT,
        "connected_devices": list(devices.keys()),
    }


@app.get("/api/local_ip")
async def local_ip_endpoint():
    return {"ip": get_local_ip()}


@app.post("/api/register_files")
async def register_files_for_download(req: RegisterFilesRequest):
    cleanup_registered_files()
    items = []
    missing = []
    for p in req.file_paths:
        abs_p = os.path.abspath(p)
        if not os.path.isfile(abs_p):
            missing.append(p)
            continue
        token = uuid.uuid4().hex
        name = os.path.basename(abs_p)
        size = os.path.getsize(abs_p)
        registered_files[token] = {
            "path": abs_p,
            "filename": name,
            "size": size,
            "created_at": time.time(),
        }
        items.append({
            "token": token,
            "filename": name,
            "size": size,
            "url_path": f"/api/download/{token}",
        })
    if missing:
        raise HTTPException(status_code=400, detail=f"Files not found on PC: {missing}")
    return {"status": "success", "files": items}


@app.get("/api/download/{identifier:path}")
async def download_file(identifier: str):
    cleanup_registered_files()
    decoded_id = urllib.parse.unquote(identifier)
    target_path = None
    display_name = None
    cleanup_token = None

    if decoded_id in registered_files:
        info = registered_files[decoded_id]
        target_path = info["path"]
        display_name = info["filename"]
        cleanup_token = decoded_id
    else:
        staged_path = os.path.join(STAGING_DIR, os.path.basename(decoded_id))
        if os.path.isfile(staged_path):
            target_path = staged_path
            display_name = os.path.basename(staged_path)

    if not target_path or not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="File not found")

    total_size = os.path.getsize(target_path)

    async def file_streamer():
        sent = 0
        completed = False
        chunk_size = 256 * 1024
        await broadcast_ui({
            "type": "transfer_start",
            "direction": "pc_to_mobile",
            "filename": display_name,
            "total": total_size,
        })
        last_emit = 0.0
        try:
            with open(target_path, "rb") as f:
                while True:
                    chunk = await run_in_threadpool(f.read, chunk_size)
                    if not chunk:
                        break
                    sent += len(chunk)
                    now = time.time()
                    if total_size > 0 and (now - last_emit > 0.25 or sent == total_size):
                        last_emit = now
                        pct = int((sent / total_size) * 100)
                        await broadcast_ui({
                            "type": "transfer_progress",
                            "direction": "pc_to_mobile",
                            "filename": display_name,
                            "percent": pct,
                            "transferred": sent,
                            "total": total_size,
                        })
                    yield chunk
            completed = (sent == total_size)
        finally:
            if completed:
                if cleanup_token:
                    registered_files.pop(cleanup_token, None)
                if target_path.startswith(STAGING_DIR) and os.path.exists(target_path):
                    try:
                        os.remove(target_path)
                    except Exception:
                        pass
                await broadcast_ui({
                    "type": "transfer_complete",
                    "direction": "pc_to_mobile",
                    "filename": display_name,
                    "total": total_size,
                })
            else:
                await broadcast_ui({
                    "type": "transfer_error",
                    "direction": "pc_to_mobile",
                    "filename": display_name,
                    "error": "Transfer interrupted before completion",
                })

    encoded_name = urllib.parse.quote(display_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "Content-Length": str(total_size),
    }
    return StreamingResponse(file_streamer(), media_type="application/octet-stream", headers=headers)


async def _save_uploaded_stream(upload: UploadFile) -> str:
    save_path = resolve_unique_save_path(PC_SHARE_DIR, upload.filename or "shared_file")
    filename = os.path.basename(save_path)
    total_size = upload.size if upload.size else 0

    await broadcast_ui({
        "type": "transfer_start",
        "direction": "mobile_to_pc",
        "filename": filename,
        "total": total_size,
    })

    written = 0
    last_emit = 0.0
    chunk_size = 256 * 1024

    try:
        with open(save_path, "wb") as buffer:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                await run_in_threadpool(buffer.write, chunk)
                written += len(chunk)
                now = time.time()
                if now - last_emit > 0.25:
                    last_emit = now
                    pct = int((written / total_size) * 100) if total_size > 0 else 50
                    await broadcast_ui({
                        "type": "transfer_progress",
                        "direction": "mobile_to_pc",
                        "filename": filename,
                        "percent": min(99, pct),
                        "transferred": written,
                        "total": total_size or written,
                    })
    except Exception as e:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
        await broadcast_ui({
            "type": "transfer_error",
            "direction": "mobile_to_pc",
            "filename": filename,
            "error": str(e),
        })
        raise

    await broadcast_ui({
        "type": "transfer_complete",
        "direction": "mobile_to_pc",
        "filename": filename,
        "path": save_path,
        "total": written,
    })
    logger.info(f"Mobile Bridge: Received file from mobile -> {save_path} ({written} bytes)")
    return save_path


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    save_path = await _save_uploaded_stream(file)
    return {"status": "success", "path": save_path, "filename": os.path.basename(save_path)}


@app.post("/api/upload_batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    saved = []
    errors = []
    for file in files:
        try:
            save_path = await _save_uploaded_stream(file)
            saved.append(save_path)
        except Exception as e:
            logger.error(f"Mobile Bridge: Failed saving {file.filename} -> {e}")
            errors.append({"file": file.filename, "error": str(e)})
    return {
        "status": "success" if not errors else ("partial" if saved else "error"),
        "count": len(saved),
        "saved": saved,
        "errors": errors,
    }


@app.post("/api/send_to_device/{device_id}")
async def send_files_from_ui_to_device(device_id: str, files: List[UploadFile] = File(...)):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' offline.")
    cleanup_registered_files()
    pc_ip = get_local_ip()
    download_items = []
    temp_paths = []
    tokens = []
    try:
        for upload in files:
            safe_name = os.path.basename(upload.filename or f"file_{int(time.time())}")
            temp_path = os.path.join(STAGING_DIR, f"{uuid.uuid4().hex}_{safe_name}")
            written = 0
            with open(temp_path, "wb") as buffer:
                while True:
                    chunk = await upload.read(256 * 1024)
                    if not chunk:
                        break
                    await run_in_threadpool(buffer.write, chunk)
                    written += len(chunk)
            temp_paths.append(temp_path)
            token = uuid.uuid4().hex
            tokens.append(token)
            registered_files[token] = {
                "path": temp_path,
                "filename": safe_name,
                "size": written,
                "created_at": time.time(),
            }
            download_items.append({
                "url": f"http://{pc_ip}:{PORT}/api/download/{token}",
                "filename": safe_name,
            })

        timeout = max(90.0, 30.0 * len(download_items))
        resp = await send_device_request(
            device_id,
            {"type": "pull_files", "files": download_items},
            timeout=timeout,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Transfer failed")
        return {"status": "success", "result": resp.get("result"), "files": [i["filename"] for i in download_items]}
    finally:
        for t in tokens:
            registered_files.pop(t, None)
        for p in temp_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@app.post("/api/transfer")
async def handle_structured_transfer(req: TransferRequest):
    if not devices:
        raise HTTPException(status_code=404, detail="No mobile device connected.")
    if req.device_id and req.device_id not in devices:
        raise HTTPException(status_code=404, detail=f"Device '{req.device_id}' offline.")
    target_device = req.device_id if req.device_id else next(iter(devices.keys()))
    pc_ip = get_local_ip()
    cleanup_registered_files()

    if req.direction == "pc_to_mobile":
        missing = [p for p in req.file_paths if not os.path.isfile(p)]
        if missing:
            raise HTTPException(status_code=400, detail=f"Files not found on PC: {missing}")

        download_items = []
        tokens = []
        for p in req.file_paths:
            abs_p = os.path.abspath(p)
            token = uuid.uuid4().hex
            tokens.append(token)
            name = os.path.basename(abs_p)
            registered_files[token] = {
                "path": abs_p,
                "filename": name,
                "size": os.path.getsize(abs_p),
                "created_at": time.time(),
            }
            download_items.append({
                "url": f"http://{pc_ip}:{PORT}/api/download/{token}",
                "filename": name,
            })

        timeout = max(90.0, 30.0 * len(download_items))
        try:
            resp = await send_device_request(
                target_device,
                {"type": "pull_files", "files": download_items},
                timeout=timeout,
            )
        finally:
            for t in tokens:
                registered_files.pop(t, None)

        if resp.get("returncode", 0) != 0 or resp.get("error"):
            return {
                "status": "error",
                "error": resp.get("error") or resp.get("result") or "Failed to transfer files to phone",
            }
        return {
            "status": "success",
            "device_id": target_device,
            "destination": "/sdcard/JarvisShare",
            "files": resp.get("saved_files", [i["filename"] for i in download_items]),
            "detail": resp.get("result"),
        }

    elif req.direction == "mobile_to_pc":
        timeout = max(90.0, 30.0 * len(req.file_paths))
        resp = await send_device_request(
            target_device,
            {
                "type": "push_files",
                "file_paths": req.file_paths,
                "upload_url": f"http://{pc_ip}:{PORT}/api/upload",
            },
            timeout=timeout,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            return {
                "status": "error",
                "error": resp.get("error") or resp.get("result") or "Failed to fetch files from phone",
            }
        return {
            "status": "success",
            "device_id": target_device,
            "destination": PC_SHARE_DIR,
            "files": resp.get("saved_files", [os.path.basename(p) for p in req.file_paths]),
            "detail": resp.get("result"),
        }

    raise HTTPException(status_code=400, detail=f"Unsupported direction: {req.direction}")


@app.post("/api/action/{device_id}")
async def trigger_quick_action(device_id: str, req: QuickActionRequest):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' offline.")
    pc_ip = get_local_ip()
    action = req.action.lower().strip()

    if action == "ring":
        cmd = (
            "termux-vibrate -d 1500 && "
            "termux-notification --title 'J.A.R.V.I.S Alert' --content 'PC is paging your device' --priority max --sound && "
            "termux-toast -g middle 'J.A.R.V.I.S is ringing your phone!'"
        )
        resp = await send_device_request(device_id, {"type": "command", "command": cmd}, timeout=20.0)
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Failed to ring phone")
        return {"status": "success", "result": resp.get("result") or "Phone alerted."}

    elif action == "clipboard_get":
        resp = await send_device_request(
            device_id,
            {"type": "command", "command": "termux-clipboard-get"},
            timeout=15.0,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Failed to read phone clipboard")
        clip_text = resp.get("result", "")
        if clip_text:
            await run_in_threadpool(set_pc_clipboard_text, clip_text)
        return {
            "status": "success",
            "clipboard": clip_text,
            "result": "Phone clipboard copied to PC!" if clip_text else "Phone clipboard is empty.",
        }

    elif action == "clipboard_set":
        text = req.payload
        if not text:
            text = await run_in_threadpool(get_pc_clipboard_text)
        if not text:
            raise HTTPException(status_code=400, detail="PC clipboard is empty.")
        resp = await send_device_request(
            device_id,
            {"type": "clipboard_set", "text": text},
            timeout=15.0,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Failed to set phone clipboard")
        return {"status": "success", "result": resp.get("result") or "Clipboard updated on phone."}

    elif action == "screenshot":
        resp = await send_device_request(
            device_id,
            {"type": "push_files", "file_paths": ["__latest_screenshot__"], "upload_url": f"http://{pc_ip}:{PORT}/api/upload"},
            timeout=40.0,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Could not fetch screenshot")
        return {"status": "success", "result": resp.get("result")}

    elif action == "latest_photo":
        resp = await send_device_request(
            device_id,
            {"type": "push_files", "file_paths": ["__latest_photo__"], "upload_url": f"http://{pc_ip}:{PORT}/api/upload"},
            timeout=45.0,
        )
        if resp.get("returncode", 0) != 0 or resp.get("error"):
            raise HTTPException(status_code=500, detail=resp.get("error") or resp.get("result") or "Could not fetch latest photo")
        return {"status": "success", "result": resp.get("result")}

    raise HTTPException(status_code=400, detail=f"Unknown quick action: {action}")


@app.get("/api/qr")
async def get_qr():
    ip = get_local_ip()
    data = f"curl -s http://{ip}:{PORT}/api/setup | python"
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(5, 8, 20), back_color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


SETUP_SCRIPT_TEMPLATE = r'''import asyncio
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

SERVER_IP = "__SERVER_IP__"
SERVER_PORT = __SERVER_PORT__
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".gif"}

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "--quiet"])
    import websockets


def _run_sync(cmd, timeout=4):
    try:
        return subprocess.check_output(
            cmd, timeout=timeout, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _toast_sync(message: str):
    try:
        subprocess.Popen(
            ["termux-toast", str(message)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def setup_environment():
    try:
        subprocess.Popen(["termux-wake-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    try:
        os.makedirs("/sdcard/JarvisShare", exist_ok=True)
    except Exception:
        pass

    home = os.path.expanduser("~")
    bin_dir = os.path.join(home, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    config_path = os.path.join(home, ".jarvis_bridge_config.json")
    try:
        with open(config_path, "w", encoding="utf-8") as cf:
            json.dump({"server_ip": SERVER_IP, "server_port": SERVER_PORT}, cf)
    except Exception:
        pass

    bridge_script_path = os.path.join(home, ".jarvis_bridge.py")
    try:
        with urllib.request.urlopen(f"http://{SERVER_IP}:{SERVER_PORT}/api/setup", timeout=10) as resp:
            script_bytes = resp.read()
            if script_bytes and b"connect_jarvis" in script_bytes:
                with open(bridge_script_path, "wb") as bf:
                    bf.write(script_bytes)
    except Exception:
        pass

    share_uploader = os.path.join(home, ".jarvis_share_upload.py")
    uploader_code = r"""import http.client
import json
import os
import subprocess
import sys
import urllib.parse
import uuid

DEFAULT_SERVER = "http://__SERVER_IP__:__SERVER_PORT__"

def get_server_url():
    cfg = os.path.expanduser("~/.jarvis_bridge_config.json")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
            ip = data.get("server_ip")
            port = data.get("server_port")
            if ip and port:
                return f"http://{ip}:{port}"
    except Exception:
        pass
    return DEFAULT_SERVER

def toast(msg):
    try:
        subprocess.Popen(["termux-toast", str(msg)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def upload_file(filepath):
    if not os.path.isfile(filepath):
        toast("Jarvis: File not found")
        return
    filename = os.path.basename(filepath)
    safe_filename = filename.replace('"', '_').replace('\r', '').replace('\n', '')
    file_size = os.path.getsize(filepath)
    boundary = uuid.uuid4().hex
    toast(f"Sending {filename} to Jarvis PC...")

    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    total_length = len(header) + file_size + len(footer)

    parsed = urllib.parse.urlsplit(f"{get_server_url()}/api/upload")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=180)
    try:
        conn.putrequest("POST", parsed.path or "/api/upload")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(total_length))
        conn.endheaders()
        conn.send(header)
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(262144)
                if not chunk:
                    break
                conn.send(chunk)
        conn.send(footer)
        resp = conn.getresponse()
        resp.read()
        if resp.status == 200:
            toast(f"Sent {filename} to Jarvis PC!")
        else:
            toast(f"Upload failed: HTTP {resp.status}")
    except Exception as e:
        toast(f"Jarvis Upload Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        upload_file(arg)
"""
    try:
        with open(share_uploader, "w", encoding="utf-8") as f:
            f.write(uploader_code)
        editor_hook = os.path.join(bin_dir, "termux-file-editor")
        with open(editor_hook, "w", encoding="utf-8") as f:
            f.write("#!/data/data/com.termux/files/usr/bin/sh\n")
            f.write(f'exec "{sys.executable}" "{share_uploader}" "$@"\n')
        os.chmod(editor_hook, 0o755)
    except Exception:
        pass


def get_device_name():
    model = _run_sync(["getprop", "ro.product.model"])
    brand = _run_sync(["getprop", "ro.product.brand"])
    market = _run_sync(["getprop", "ro.product.marketname"])

    if market and market.lower() not in ("", "unknown"):
        base = market
    elif model and model.lower() not in ("", "unknown"):
        base = model
        if brand and brand.lower() not in ("", "unknown") and not model.lower().startswith(brand.lower()):
            base = f"{brand} {model}"
    else:
        hn = ""
        try:
            hn = socket.gethostname()
        except Exception:
            pass
        base = hn if (hn and hn.lower() != "localhost") else "android_device"

    base = base.strip().replace(" ", "_") or "android_device"

    try:
        aid = _run_sync(["settings", "get", "secure", "android_id"], timeout=2)
        if aid and len(aid) >= 4 and "Failure" not in aid:
            base = f"{base}_{aid[:4]}"
    except Exception:
        pass

    return base


def get_battery():
    try:
        out = subprocess.check_output(["termux-battery-status"], timeout=4, stderr=subprocess.DEVNULL)
        data = json.loads(out.decode("utf-8", errors="replace"))
        level = int(data.get("percentage", -1))
        if level < 0:
            return None
        return {
            "level": level,
            "charging": data.get("status") in ("CHARGING", "FULL"),
            "temperature": data.get("temperature"),
        }
    except Exception:
        return None


def get_storage():
    try:
        target = "/sdcard" if os.path.exists("/sdcard") else os.path.expanduser("~")
        usage = shutil.disk_usage(target)
        free_gb = round(usage.free / (1024 ** 3), 1)
        total_gb = round(usage.total / (1024 ** 3), 1)
        return {"free_gb": free_gb, "total_gb": total_gb}
    except Exception:
        return None


def get_network_info():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((SERVER_IP, SERVER_PORT))
        ip = s.getsockname()[0]
        s.close()
        return {"ip": ip}
    except Exception:
        return None


async def run_shell_command(cmd: str, timeout: float = 85.0):
    proc = None
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                await proc.wait()
            except Exception:
                pass
            return "Command timed out on mobile device.", -1

        out_str = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
        err_str = stderr.decode("utf-8", errors="replace").strip() if stderr else ""
        if out_str and err_str:
            combined = f"{out_str}\n{err_str}" if proc.returncode != 0 else out_str
        else:
            combined = out_str if out_str else err_str
        return combined, (proc.returncode if proc.returncode is not None else 0)
    except Exception as e:
        return str(e), -1


def _resolve_unique_mobile_path(directory: str, filename: str) -> str:
    os.makedirs(directory, exist_ok=True)
    safe_name = os.path.basename(filename.strip()) or f"file_{int(time.time())}"
    candidate = os.path.join(directory, safe_name)
    if not os.path.exists(candidate):
        return candidate
    name, ext = os.path.splitext(safe_name)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{name}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _download_single_file(url: str, dest_dir: str, filename: str) -> str:
    dest_path = _resolve_unique_mobile_path(dest_dir, filename)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest_path, "wb") as out:
            shutil.copyfileobj(resp, out, length=256 * 1024)
        return dest_path
    except Exception:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise


def _resolve_special_mobile_path(token_or_path: str) -> str:
    if token_or_path == "__latest_photo__":
        search_dirs = ["/sdcard/DCIM/Camera", "/sdcard/DCIM", "/sdcard/Pictures"]
        label = "camera photo"
    elif token_or_path == "__latest_screenshot__":
        search_dirs = ["/sdcard/Pictures/Screenshots", "/sdcard/DCIM/Screenshots"]
        label = "screenshot"
    else:
        return token_or_path

    candidates = []
    for d in search_dirs:
        if os.path.isdir(d):
            try:
                for entry in os.scandir(d):
                    if entry.is_file() and not entry.name.startswith("."):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in IMAGE_EXTENSIONS:
                            try:
                                candidates.append((entry.stat().st_mtime, entry.path))
                            except Exception:
                                pass
            except Exception:
                pass
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    raise FileNotFoundError(f"No recent {label} found on phone.")


def _upload_single_file(filepath: str, upload_url: str):
    real_path = _resolve_special_mobile_path(filepath)
    if not os.path.isfile(real_path):
        raise FileNotFoundError(f"File not found on phone: {real_path}")
    filename = os.path.basename(real_path)
    safe_filename = filename.replace('"', '_').replace('\r', '').replace('\n', '')
    file_size = os.path.getsize(real_path)
    boundary = uuid.uuid4().hex

    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    total_length = len(header) + file_size + len(footer)

    parsed = urllib.parse.urlsplit(upload_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=180)
    try:
        conn.putrequest("POST", parsed.path or "/api/upload")
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(total_length))
        conn.endheaders()
        conn.send(header)
        with open(real_path, "rb") as f:
            while True:
                chunk = f.read(262144)
                if not chunk:
                    break
                conn.send(chunk)
        conn.send(footer)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8", errors="replace")
        if resp.status >= 400:
            raise RuntimeError(f"Upload failed with HTTP {resp.status}: {resp_body}")
        return json.loads(resp_body), filename
    finally:
        conn.close()


async def telemetry_loop(ws):
    while True:
        await asyncio.sleep(25)
        b = await asyncio.to_thread(get_battery)
        s = await asyncio.to_thread(get_storage)
        try:
            await ws.send(json.dumps({
                "type": "battery_update",
                "battery": b,
                "storage": s,
            }))
        except Exception:
            return


async def handle_ws_message(ws, data: dict):
    msg_type = data.get("type")
    req_id = data.get("req_id")

    try:
        if msg_type == "command":
            cmd = data.get("command", "")
            result, code = await run_shell_command(cmd)
            await ws.send(json.dumps({
                "type": "response",
                "req_id": req_id,
                "result": result,
                "returncode": code,
            }))

        elif msg_type == "pull_files":
            files = data.get("files", [])
            saved = []
            errors = []
            for item in files:
                url = item.get("url")
                name = os.path.basename(item.get("filename") or "file")
                try:
                    dest = await asyncio.to_thread(_download_single_file, url, "/sdcard/JarvisShare", name)
                    saved.append(dest)
                except Exception as e:
                    errors.append(f"{name}: {e}")
            if saved:
                _toast_sync(f"Jarvis: Received {len(saved)} file(s)")
            await ws.send(json.dumps({
                "type": "response",
                "req_id": req_id,
                "result": f"Saved {len(saved)} files to /sdcard/JarvisShare" if not errors else "; ".join(errors),
                "saved_files": saved,
                "returncode": 0 if not errors else 1,
            }))

        elif msg_type == "push_files":
            paths = data.get("file_paths", [])
            upload_url = data.get("upload_url")
            uploaded = []
            errors = []
            for p in paths:
                try:
                    _, fname = await asyncio.to_thread(_upload_single_file, p, upload_url)
                    uploaded.append(fname)
                except Exception as e:
                    errors.append(str(e))
            if uploaded:
                _toast_sync(f"Jarvis: Sent {len(uploaded)} file(s) to PC")
            await ws.send(json.dumps({
                "type": "response",
                "req_id": req_id,
                "result": f"Uploaded {len(uploaded)} files: {', '.join(uploaded)}" if not errors else "; ".join(errors),
                "saved_files": uploaded,
                "returncode": 0 if not errors else 1,
            }))

        elif msg_type == "clipboard_set":
            text = data.get("text", "")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "termux-clipboard-set",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=text.encode("utf-8")),
                    timeout=10.0,
                )
                if proc.returncode == 0:
                    _toast_sync("Clipboard synced from Jarvis PC")
                    await ws.send(json.dumps({
                        "type": "response",
                        "req_id": req_id,
                        "result": "Clipboard set on mobile device.",
                        "returncode": 0,
                    }))
                else:
                    err_msg = stderr_bytes.decode("utf-8", errors="replace").strip() or "termux-clipboard-set failed"
                    await ws.send(json.dumps({
                        "type": "response",
                        "req_id": req_id,
                        "result": err_msg,
                        "returncode": proc.returncode or 1,
                    }))
            except Exception as e:
                await ws.send(json.dumps({
                    "type": "response",
                    "req_id": req_id,
                    "result": f"Clipboard error on phone (ensure termux-api is installed): {e}",
                    "returncode": 1,
                }))
    except Exception as e:
        try:
            await ws.send(json.dumps({
                "type": "response",
                "req_id": req_id,
                "result": str(e),
                "returncode": -1,
            }))
        except Exception:
            pass


async def connect_jarvis():
    uri = f"ws://{SERVER_IP}:{SERVER_PORT}/ws"
    device_id = await asyncio.to_thread(get_device_name)
    print(f"Connecting to Jarvis at {uri}...")
    async with websockets.connect(uri, ping_interval=20, ping_timeout=20, max_size=None) as websocket:
        print(f"Connected as: {device_id} (Android Share -> Termux enabled)")
        await websocket.send(json.dumps({
            "type": "handshake",
            "device_id": device_id,
            "battery": await asyncio.to_thread(get_battery),
            "storage": await asyncio.to_thread(get_storage),
            "network": await asyncio.to_thread(get_network_info),
        }))
        t_task = asyncio.create_task(telemetry_loop(websocket))
        try:
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data.get("type") == "system" and data.get("command") == "shutdown_bridge":
                    return False
                asyncio.create_task(handle_ws_message(websocket, data))
        finally:
            t_task.cancel()
    return True


async def main_loop():
    await asyncio.to_thread(setup_environment)
    while True:
        try:
            should_reconnect = await connect_jarvis()
            if should_reconnect is False:
                print("Bridge explicitly shut down by Jarvis PC.")
                break
        except Exception:
            print("Disconnected or Jarvis offline. Retrying in 3 seconds...")
        await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nMobile Bridge stopped by user.")
'''


@app.get("/api/setup", response_class=PlainTextResponse)
async def get_setup_script(request: Request):
    ip_address = get_local_ip()
    script = SETUP_SCRIPT_TEMPLATE.replace("__SERVER_IP__", ip_address).replace("__SERVER_PORT__", str(PORT))
    return script


@app.websocket("/ws/ui")
async def ui_websocket(websocket: WebSocket):
    await websocket.accept()
    ui_clients.append(websocket)
    try:
        await websocket.send_json({"type": "init", "devices": serialize_devices()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ui_clients:
            ui_clients.remove(websocket)
    except Exception as e:
        logger.error(f"UI WebSocket Error -> {e}")
        if websocket in ui_clients:
            ui_clients.remove(websocket)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    device_id = None
    try:
        handshake = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
        if handshake.get("type") == "handshake" and handshake.get("device_id"):
            device_id = str(handshake.get("device_id")).strip()

            old_ws = devices.get(device_id)
            if old_ws is not None and old_ws is not websocket:
                fail_pending_requests_for_device(device_id, "Device reconnected")
                try:
                    await old_ws.close(code=1000, reason="Replaced by new connection")
                except Exception:
                    pass

            devices[device_id] = websocket
            device_meta[device_id] = {
                "battery": handshake.get("battery"),
                "storage": handshake.get("storage"),
                "network": handshake.get("network"),
            }
            update_state_file()
            logger.info(f"Mobile Bridge: Device Connected -> {device_id}")
            await broadcast_ui({
                "type": "device_connected",
                "device_id": device_id,
                "battery": handshake.get("battery"),
                "storage": handshake.get("storage"),
                "network": handshake.get("network"),
            })
            await websocket.send_json({"type": "welcome", "msg": "Connected to Jarvis PC"})
        else:
            logger.warning("Mobile Bridge: Invalid handshake.")
            await websocket.close()
            return

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "response":
                req_id = data.get("req_id")
                fut = pending_requests.get(req_id)
                if fut is not None and not fut.done():
                    fut.set_result(data)

            elif msg_type == "battery_update":
                battery = data.get("battery")
                storage = data.get("storage")
                meta = device_meta.setdefault(device_id, {})
                meta["battery"] = battery
                if storage:
                    meta["storage"] = storage
                await broadcast_ui({
                    "type": "battery_update",
                    "device_id": device_id,
                    "battery": battery,
                    "storage": storage,
                })

            elif msg_type == "error":
                logger.error(f"Mobile Bridge: Phone error ({device_id}) -> {data.get('message')}")

    except WebSocketDisconnect:
        if device_id:
            logger.warning(f"Mobile Bridge: Device Disconnected -> {device_id}")
            fail_pending_requests_for_device(device_id, "Device disconnected")
            if devices.get(device_id) is websocket:
                del devices[device_id]
                device_meta.pop(device_id, None)
                update_state_file()
                await broadcast_ui({"type": "device_disconnected", "device_id": device_id})
    except Exception as e:
        logger.error(f"Mobile Bridge: WebSocket Error -> {e}")
        if device_id:
            fail_pending_requests_for_device(device_id, f"WebSocket error: {e}")
            if devices.get(device_id) is websocket:
                del devices[device_id]
                device_meta.pop(device_id, None)
                update_state_file()
                await broadcast_ui({"type": "device_disconnected", "device_id": device_id})


@app.post("/api/disconnect/{device_id}")
async def disconnect_device(device_id: str):
    if device_id not in devices:
        raise HTTPException(status_code=404, detail="Device not found")

    ws = devices.pop(device_id, None)
    device_meta.pop(device_id, None)
    fail_pending_requests_for_device(device_id, "Device manually disconnected")
    update_state_file()
    await broadcast_ui({"type": "device_disconnected", "device_id": device_id})

    if ws is not None:
        try:
            await asyncio.wait_for(
                ws.send_json({"type": "system", "command": "shutdown_bridge"}),
                timeout=2.0,
            )
        except Exception:
            pass
        try:
            await asyncio.wait_for(ws.close(code=1000, reason="Disconnected by user"), timeout=2.0)
        except Exception:
            pass

    logger.info(f"Mobile Bridge: Disconnected device -> {device_id}")
    return {"status": "success", "msg": "Device disconnected"}


@app.post("/api/execute")
async def execute_command(req: CommandRequest):
    if req.target_device not in devices:
        logger.warning(f"Mobile Bridge: Execution failed, '{req.target_device}' is offline.")
        raise HTTPException(status_code=404, detail=f"Device '{req.target_device}' offline.")

    logger.info(f"Mobile Bridge: Sending command to {req.target_device}: {req.command}")
    await broadcast_ui({
        "type": "command_start",
        "device_id": req.target_device,
        "command": req.command,
    })

    resp = await send_device_request(
        req.target_device,
        {"type": "command", "command": req.command},
        timeout=req.timeout or 90.0,
    )

    if "error" in resp:
        logger.error(f"Mobile Bridge: Command error on {req.target_device} -> {resp['error']}")
        await broadcast_ui({
            "type": "command_complete",
            "device_id": req.target_device,
            "command": req.command,
            "returncode": resp.get("returncode", -1),
        })
        return {"error": resp["error"], "returncode": resp.get("returncode", -1), "status": "error"}

    result_text = resp.get("result", "")
    returncode = resp.get("returncode", 0)
    logger.info(f"Mobile Bridge: Response from {req.target_device} (exit={returncode})")

    await broadcast_ui({
        "type": "command_complete",
        "device_id": req.target_device,
        "command": req.command,
        "returncode": returncode,
    })

    return {
        "result": result_text,
        "returncode": returncode,
        "status": "success" if returncode == 0 else "error",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")