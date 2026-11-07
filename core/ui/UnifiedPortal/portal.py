import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool

from core.logger.logger import logger

DEFAULT_RAG_PORT = 8080
DEFAULT_MOBILE_PORT = 8090
DEFAULT_PORTAL_PORT = 8000

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)


def _check_backend(url: str) -> bool:
    try:
        r = requests.get(url, timeout=3.0)
        return 200 <= r.status_code < 400
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Unified Portal ready on port {app.state.portal_port} "
        f"(RAG: {app.state.rag_port} | Mobile: {app.state.mobile_port})"
    )
    yield


app = FastAPI(title="Jarvis Unified Portal", lifespan=lifespan)
app.state.rag_port = int(os.getenv("JARVIS_RAG_PORT", DEFAULT_RAG_PORT))
app.state.mobile_port = int(os.getenv("JARVIS_MOBILE_PORT", DEFAULT_MOBILE_PORT))
app.state.portal_port = int(os.getenv("JARVIS_PORTAL_PORT", DEFAULT_PORTAL_PORT))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "rag_port": request.app.state.rag_port,
            "mobile_port": request.app.state.mobile_port,
            "portal_port": request.app.state.portal_port,
        },
    )


@app.get("/health")
async def health(request: Request):
    rag_port = request.app.state.rag_port
    mobile_port = request.app.state.mobile_port
    rag_ok = await run_in_threadpool(_check_backend, f"http://127.0.0.1:{rag_port}/api/status")
    mobile_ok = await run_in_threadpool(_check_backend, f"http://127.0.0.1:{mobile_port}/api/health")
    overall = "online" if (rag_ok and mobile_ok) else "degraded"
    return {
        "status": overall,
        "portal": "online",
        "rag": {"status": "online" if rag_ok else "offline", "port": rag_port},
        "mobile": {"status": "online" if mobile_ok else "offline", "port": mobile_port},
    }


def _parse_args():
    p = argparse.ArgumentParser(description="Jarvis Unified Portal")
    p.add_argument("--rag-port", type=int, default=int(os.getenv("JARVIS_RAG_PORT", DEFAULT_RAG_PORT)))
    p.add_argument("--mobile-port", type=int, default=int(os.getenv("JARVIS_MOBILE_PORT", DEFAULT_MOBILE_PORT)))
    p.add_argument("--portal-port", type=int, default=int(os.getenv("JARVIS_PORTAL_PORT", DEFAULT_PORTAL_PORT)))
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    app.state.rag_port = args.rag_port
    app.state.mobile_port = args.mobile_port
    app.state.portal_port = args.portal_port

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.portal_port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )