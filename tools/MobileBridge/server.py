import os
import sys
import io
import asyncio
import uuid
import json
import socket
import shutil
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    import qrcode
    from qrcode.image.pil import PilImage
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]"])
    import qrcode
    from qrcode.image.pil import PilImage

try:
    import multipart
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-multipart"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.logger.logger import logger

PORT = 8090
devices = {}
device_meta = {}
ui_clients = []
pending_requests = {}
STATE_FILE = os.path.join(PROJECT_ROOT, "Data", "SessionCookies", "connected_devices.json")

USER_HOME = os.path.expanduser("~")
PC_SHARE_DIR = os.path.join(USER_HOME, "Documents", "Jarvis", "JarvisShare")
os.makedirs(PC_SHARE_DIR, exist_ok=True)

STAGING_DIR = os.path.join(PROJECT_ROOT, "Data", "Staging")
os.makedirs(STAGING_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    update_state_file()
    logger.info(f"Mobile Bridge Service Started. Devices: {list(devices.keys())}")
    yield

app = FastAPI(title="Jarvis Mobile Bridge", lifespan=lifespan)

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)

class CommandRequest(BaseModel):
    target_device: str
    command: str

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def update_state_file():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(devices.keys()), f)
    except Exception as e:
        logger.error(f"Mobile Bridge: Failed to update state file -> {e}")

def serialize_devices():
    out = []
    for did in devices.keys():
        meta = device_meta.get(did, {})
        out.append({"id": did, "battery": meta.get("battery")})
    return out

async def broadcast_ui(message: dict):
    dead = []
    for c in ui_clients:
        try:
            await c.send_json(message)
        except Exception:
            dead.append(c)
    for c in dead:
        if c in ui_clients:
            ui_clients.remove(c)

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(STAGING_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename)
    raise HTTPException(status_code=404)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    save_path = os.path.join(PC_SHARE_DIR, file.filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success", "path": save_path}

@app.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    ip_address = get_local_ip()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"ip_address": ip_address, "port": PORT},
    )

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
    img = qr.make_image(fill_color="#050814", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )

@app.get("/api/setup", response_class=PlainTextResponse)
async def get_setup_script(request: Request):
    ip_address = request.url.hostname or get_local_ip()
    
    script = f'''import asyncio
import json
import subprocess
import socket
import sys

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

def _run(cmd, timeout=3):
    try:
        return subprocess.check_output(
            cmd, timeout=timeout, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return ""

def get_device_name():
    model = _run(["getprop", "ro.product.model"])
    brand = _run(["getprop", "ro.product.brand"])
    market = _run(["getprop", "ro.product.marketname"])

    if market and market.lower() not in ("", "unknown"):
        base = market
    elif model and model.lower() not in ("", "unknown"):
        base = model
        if brand and brand.lower() not in ("", "unknown") and not model.lower().startswith(brand.lower()):
            base = f"{{brand}} {{model}}"
    else:
        hn = ""
        try:
            hn = socket.gethostname()
        except Exception:
            pass
        if hn and hn.lower() != "localhost":
            base = hn
        else:
            base = "android_device"

    base = base.strip().replace(" ", "_")
    if not base:
        base = "android_device"

    try:
        aid = _run(["settings", "get", "secure", "android_id"], timeout=2)
        if aid and len(aid) >= 4:
            base = f"{{base}}_{{aid[:4]}}"
    except Exception:
        pass

    return base

def get_battery():
    try:
        out = subprocess.check_output(["termux-battery-status"], timeout=3)
        data = json.loads(out.decode())
        level = int(data.get("percentage", -1))
        if level < 0:
            return None
        return {{
            "level": level,
            "charging": data.get("status") in ("CHARGING", "FULL"),
            "temperature": data.get("temperature"),
        }}
    except Exception:
        return None

async def battery_loop(ws):
    while True:
        await asyncio.sleep(30)
        b = get_battery()
        if b:
            try:
                await ws.send(json.dumps({{"type": "battery_update", "battery": b}}))
            except Exception:
                return

async def connect_jarvis():
    uri = "ws://{ip_address}:{PORT}/ws"
    device_id = get_device_name()
    print(f"Connecting to Jarvis at {{uri}}...")
    async with websockets.connect(uri) as websocket:
        print(f"Successfully Connected as: {{device_id}}")
        await websocket.send(json.dumps({{
            "type": "handshake",
            "device_id": device_id,
            "battery": get_battery(),
        }}))
        b_task = asyncio.create_task(battery_loop(websocket))
        try:
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                if data.get("type") == "command":
                    cmd = data.get("command")
                    req_id = data.get("req_id")
                    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, err = process.communicate()
                    result = out.decode() if out else err.decode()
                    await websocket.send(json.dumps({{"type": "response", "req_id": req_id, "result": result}}))
                elif data.get("type") == "system" and data.get("command") == "shutdown_bridge":
                    return False
        finally:
            b_task.cancel()
    return True

async def main_loop():
    while True:
        try:
            should_reconnect = await connect_jarvis()
            if should_reconnect is False:
                print("Bridge explicitly shut down by server.")
                break
        except Exception as e:
            print(f"Disconnected or Jarvis offline. Retrying in 3 seconds...")
        await asyncio.sleep(3)

asyncio.run(main_loop())
'''
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    device_id = None
    try:
        handshake = await websocket.receive_json()
        if handshake.get("type") == "handshake":
            device_id = handshake.get("device_id")
            devices[device_id] = websocket
            device_meta[device_id] = {"battery": handshake.get("battery")}
            update_state_file()
            logger.info(f"Mobile Bridge: Device Connected -> {device_id}")
            await broadcast_ui({
                "type": "device_connected",
                "device_id": device_id,
                "battery": handshake.get("battery"),
            })
            await websocket.send_json({"type": "welcome", "msg": "Connected to Jarvis PC"})
        else:
            logger.warning("Mobile Bridge: Invalid handshake.")
            await websocket.close()
            return

        while True:
            data = await websocket.receive_json()
            if data.get("type") == "response":
                req_id = data.get("req_id")
                if req_id in pending_requests:
                    pending_requests[req_id].set_result(data.get("result"))
            elif data.get("type") == "battery_update":
                battery = data.get("battery")
                device_meta.setdefault(device_id, {})["battery"] = battery
                await broadcast_ui({
                    "type": "battery_update",
                    "device_id": device_id,
                    "battery": battery,
                })
            elif data.get("type") == "error":
                logger.error(f"Mobile Bridge: Phone error -> {data.get('message')}")

    except WebSocketDisconnect:
        if device_id:
            logger.warning(f"Mobile Bridge: Device Disconnected -> {device_id}")
            if device_id in devices:
                del devices[device_id]
                device_meta.pop(device_id, None)
                update_state_file()
                await broadcast_ui({"type": "device_disconnected", "device_id": device_id})
    except Exception as e:
        logger.error(f"Mobile Bridge: WebSocket Error -> {e}")
        if device_id and device_id in devices:
            del devices[device_id]
            device_meta.pop(device_id, None)
            update_state_file()
            await broadcast_ui({"type": "device_disconnected", "device_id": device_id})

@app.post("/api/disconnect/{device_id}")
async def disconnect_device(device_id: str):
    if device_id in devices:
        ws = devices[device_id]
        try:
            await ws.send_json({"type": "system", "command": "shutdown_bridge"})
            logger.info(f"Mobile Bridge: Sent shutdown command to {device_id}")
            return {"status": "success", "msg": "Disconnect signal sent"}
        except Exception as e:
            logger.error(f"Mobile Bridge: Failed to disconnect {device_id} -> {e}")
            raise HTTPException(status_code=500, detail="Failed to send disconnect signal")
    raise HTTPException(status_code=404, detail="Device not found")

@app.post("/api/execute")
async def execute_command(req: CommandRequest):
    if req.target_device not in devices:
        logger.warning(f"Mobile Bridge: Execution failed, '{req.target_device}' is offline.")
        raise HTTPException(status_code=404, detail=f"Device '{req.target_device}' offline.")

    ws = devices[req.target_device]
    req_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    pending_requests[req_id] = future

    try:
        logger.info(f"Mobile Bridge: Sending command to {req.target_device}: {req.command}")
        await ws.send_json({"type": "command", "req_id": req_id, "command": req.command})
    except Exception as e:
        logger.error(f"Mobile Bridge: Failed to send command -> {e}")
        if req_id in pending_requests:
            del pending_requests[req_id]
        raise HTTPException(status_code=500, detail="Failed to transmit command.")

    try:
        result = await asyncio.wait_for(future, timeout=12.0)
        logger.info(f"Mobile Bridge: Received response from {req.target_device}")
        return {"result": result}
    except asyncio.TimeoutError:
        logger.error(f"Mobile Bridge: Timeout waiting for {req.target_device}")
        return {"error": "Timeout: Phone did not respond in 12 seconds."}
    finally:
        if req_id in pending_requests:
            del pending_requests[req_id]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")