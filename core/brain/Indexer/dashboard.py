import socket
import threading
import time
from flask import Flask, jsonify, request, render_template_string

from core.logger.logger import logger

try:
    from werkzeug.serving import make_server
    WERKZEUG_OK = True
except ImportError:
    WERKZEUG_OK = False


_flask_app = None
_server = None
_server_thread = None
_actual_port = None
_dashboard_lock = threading.Lock()


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>J.A.R.V.I.S · Knowledge Indexer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#050914;--panel:rgba(15,23,42,.55);--panel-2:rgba(30,41,59,.5);
  --border:rgba(148,163,184,.14);--border-h:rgba(56,189,248,.45);
  --accent:#38bdf8;--accent2:#a855f7;--ok:#10b981;--warn:#f59e0b;--err:#ef4444;
  --text:#e2e8f0;--muted:#94a3b8;--muted2:#64748b;
}
html,body{min-height:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",Roboto,Helvetica,Arial,sans-serif;
  background:radial-gradient(1200px 600px at 10% -10%,rgba(56,189,248,.10),transparent 60%),
             radial-gradient(1000px 500px at 100% 100%,rgba(168,85,247,.10),transparent 60%),
             var(--bg);
  color:var(--text);display:flex;justify-content:center;padding:26px 16px;
  -webkit-font-smoothing:antialiased;
}
.shell{
  width:100%;max-width:1120px;background:var(--panel);
  border:1px solid var(--border);border-radius:20px;padding:26px;
  box-shadow:0 24px 60px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.04);
  animation:rise .45s cubic-bezier(.16,1,.3,1);
}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes slideX{0%{background-position:0% 50%}100%{background-position:200% 50%}}

/* HERO */
.hero{display:flex;justify-content:space-between;align-items:center;gap:16px;
  padding-bottom:18px;border-bottom:1px solid var(--border);margin-bottom:20px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(135deg,#0ea5e9,#6366f1,#a855f7);
  box-shadow:0 0 24px rgba(56,189,248,.4);color:#fff}
.logo svg{width:22px;height:22px}
.brand h1{font-size:19px;font-weight:800;letter-spacing:5px;color:#f0f9ff}
.brand p{font-size:10.5px;color:var(--muted);letter-spacing:2.5px;text-transform:uppercase;margin-top:3px}

.pill{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:999px;
  font-size:11.5px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;border:1px solid}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;animation:pulse 1.8s infinite}
.pill.idle{color:var(--ok);border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.07)}
.pill.scanning{color:var(--warn);border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.07)}
.pill.paused{color:var(--muted);border-color:rgba(148,163,184,.35);background:rgba(148,163,184,.07)}
.pill.error{color:var(--err);border-color:rgba(239,68,68,.35);background:rgba(239,68,68,.07)}

/* STATS */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat{display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:12px;
  background:var(--panel-2);border:1px solid var(--border);transition:transform .25s,border-color .25s}
.stat:hover{transform:translateY(-2px);border-color:var(--border-h)}
.stat .ic{width:38px;height:38px;border-radius:9px;display:grid;place-items:center;
  background:rgba(56,189,248,.09);border:1px solid rgba(56,189,248,.22);color:var(--accent);flex-shrink:0}
.stat .ic svg{width:16px;height:16px}
.stat.p .ic{background:rgba(168,85,247,.09);border-color:rgba(168,85,247,.22);color:var(--accent2)}
.stat.s .ic{background:rgba(16,185,129,.09);border-color:rgba(16,185,129,.22);color:var(--ok)}
.stat .val{font-size:19px;font-weight:800;color:#f8fafc;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stat .lb{font-size:10px;color:var(--muted);letter-spacing:1.2px;text-transform:uppercase;font-weight:700;margin-top:2px}

/* PROGRESS */
.prog{background:var(--panel-2);border:1px solid var(--border);border-radius:12px;
  padding:16px 18px;margin-bottom:20px}
.prog-head{display:flex;justify-content:space-between;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.prog-head .l{font-size:10.5px;color:var(--muted);letter-spacing:1.8px;text-transform:uppercase;font-weight:700}
.prog-head .d{font-size:11.5px;color:var(--muted);font-family:ui-monospace,Consolas,monospace}
.track{height:8px;background:rgba(2,6,23,.7);border-radius:4px;overflow:hidden}
.fill{height:100%;width:0;border-radius:4px;
  background:linear-gradient(90deg,#38bdf8,#22d3ee,#a855f7,#38bdf8);
  background-size:200% 100%;transition:width .5s cubic-bezier(.16,1,.3,1);
  animation:slideX 4s linear infinite;box-shadow:0 0 14px rgba(56,189,248,.5)}

/* TABS */
.tabs{display:flex;gap:4px;padding:5px;background:rgba(2,6,23,.55);
  border:1px solid var(--border);border-radius:12px;margin-bottom:18px;width:fit-content;
  max-width:100%;overflow-x:auto}
.tab{padding:9px 18px;border:none;background:transparent;color:var(--muted);
  font:inherit;font-size:11.5px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;
  border-radius:8px;cursor:pointer;transition:all .2s;white-space:nowrap;display:flex;align-items:center;gap:7px}
.tab:hover{color:var(--text)}
.tab.on{color:#e0f2fe;background:linear-gradient(135deg,rgba(56,189,248,.18),rgba(168,85,247,.18))}
.tab svg{width:12px;height:12px}
.tab-pane{display:none}
.tab-pane.on{display:block;animation:fade .3s ease}

/* CARD */
.card{background:linear-gradient(160deg,rgba(30,41,59,.45),rgba(2,6,23,.65));
  border:1px solid var(--border);border-radius:16px;padding:20px;margin-bottom:16px}
.card h2{font-size:10.5px;font-weight:700;letter-spacing:2.2px;text-transform:uppercase;
  color:var(--muted);margin-bottom:16px;display:flex;align-items:center;gap:9px}
.card h2 svg{width:13px;height:13px;color:var(--accent)}
.card h2 .badge{margin-left:auto;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.35);
  color:var(--accent);padding:3px 10px;border-radius:999px;font-size:10.5px;font-weight:800}

/* FORM */
.row{display:flex;gap:10px;flex-wrap:wrap}
.row input{flex:1;min-width:200px}
.field{margin-bottom:14px}
.field:last-child{margin-bottom:0}
.field label{display:block;font-size:10.5px;color:var(--muted);margin-bottom:7px;
  letter-spacing:1.2px;text-transform:uppercase;font-weight:700}
input[type=text],input[type=number],textarea{
  width:100%;background:rgba(2,6,23,.7);color:var(--text);border:1px solid var(--border);
  padding:10px 12px;border-radius:9px;font:inherit;font-size:12.5px;transition:border-color .2s,box-shadow .2s}
input:focus,textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(56,189,248,.14)}
textarea{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;line-height:1.6;resize:vertical}
.hint{font-size:10.5px;color:var(--muted2);margin-top:5px;line-height:1.5}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}

/* BUTTONS */
button{font:inherit;font-size:12px;font-weight:600;cursor:pointer;border-radius:9px;
  padding:9px 16px;border:1px solid var(--border);background:var(--panel-2);color:var(--text);
  display:inline-flex;align-items:center;gap:7px;transition:all .2s}
button:hover{border-color:var(--border-h);background:rgba(56,189,248,.1);transform:translateY(-1px)}
button:disabled{opacity:.4;cursor:not-allowed;transform:none}
button svg{width:13px;height:13px}
button.pri{background:linear-gradient(135deg,#0ea5e9,#6366f1);border-color:rgba(56,189,248,.5);
  color:#fff;box-shadow:0 0 16px rgba(56,189,248,.35)}
button.pri:hover{box-shadow:0 0 22px rgba(56,189,248,.55)}
button.dgr{background:linear-gradient(135deg,#dc2626,#ef4444);border-color:rgba(239,68,68,.5);
  color:#fff;box-shadow:0 0 16px rgba(239,68,68,.25)}
button.dgr:hover{box-shadow:0 0 22px rgba(239,68,68,.5)}
button.wrn{background:linear-gradient(135deg,#d97706,#f59e0b);border-color:rgba(245,158,11,.5);
  color:#fff;box-shadow:0 0 16px rgba(245,158,11,.25)}
button.wrn:hover{box-shadow:0 0 22px rgba(245,158,11,.5)}
button.gho{background:transparent}
.icon-btn{width:34px;height:34px;padding:0;justify-content:center;border-radius:9px}
.icon-btn.dgr{background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.3);color:var(--err);box-shadow:none}
.icon-btn.dgr:hover{background:var(--err);color:#fff;border-color:var(--err);box-shadow:0 0 16px rgba(239,68,68,.5)}
.icon-btn.acc{background:rgba(56,189,248,.08);border-color:rgba(56,189,248,.3);color:var(--accent);box-shadow:none}
.icon-btn.acc:hover{background:var(--accent);color:#0a0f24;border-color:var(--accent);box-shadow:0 0 16px rgba(56,189,248,.5)}

/* FOLDER LIST */
.folder{display:flex;align-items:center;gap:12px;padding:13px 15px;border-radius:12px;
  background:linear-gradient(145deg,rgba(30,41,59,.6),rgba(15,23,42,.8));
  border:1px solid var(--border);margin-bottom:9px;transition:border-color .25s,transform .25s;
  animation:fade .35s ease}
.folder:hover{border-color:var(--border-h);transform:translateX(3px)}
.folder .fi{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;
  background:linear-gradient(135deg,rgba(56,189,248,.15),rgba(168,85,247,.15));
  border:1px solid rgba(56,189,248,.25);color:#fbbf24;flex-shrink:0}
.folder .fi svg{width:16px;height:16px}
.folder .inf{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.folder .nm{font-size:13.5px;font-weight:700;color:#f8fafc;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.folder .tag{font-size:9px;padding:2px 7px;border-radius:999px;background:rgba(56,189,248,.15);
  border:1px solid rgba(56,189,248,.3);color:var(--accent);letter-spacing:.8px;text-transform:uppercase;font-weight:800}
.folder .meta{display:flex;gap:12px;font-size:10.5px;color:var(--muted);font-weight:600;letter-spacing:.4px}
.folder .path{font-size:10.5px;color:var(--muted2);font-family:ui-monospace,Consolas,monospace;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.folder .acts{display:flex;gap:7px;flex-shrink:0}

.empty{text-align:center;padding:38px 20px;color:var(--muted);border:1px dashed var(--border);
  border-radius:12px;font-size:12.5px;letter-spacing:.5px}

/* TOAST */
.toast{position:fixed;bottom:24px;right:24px;padding:13px 20px;border-radius:11px;
  background:linear-gradient(135deg,#10b981,#22d3ee);color:#fff;font-size:12.5px;font-weight:600;
  box-shadow:0 18px 44px rgba(16,185,129,.35);opacity:0;transform:translateY(16px);
  pointer-events:none;transition:all .3s cubic-bezier(.16,1,.3,1);z-index:100;max-width:380px}
.toast.on{opacity:1;transform:none}
.toast.err{background:linear-gradient(135deg,#dc2626,#ef4444);box-shadow:0 18px 44px rgba(239,68,68,.35)}

::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:rgba(2,6,23,.5)}
::-webkit-scrollbar-thumb{background:rgba(56,189,248,.25);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:rgba(56,189,248,.5)}

@media(max-width:880px){.stats{grid-template-columns:repeat(2,1fr)}.g2{grid-template-columns:1fr}.g4{grid-template-columns:repeat(2,1fr)}.shell{padding:20px}}
@media(max-width:520px){.stats{grid-template-columns:1fr}.hero{flex-direction:column;align-items:flex-start}
  .brand h1{font-size:16px;letter-spacing:3px}.tab span{display:none}.toast{left:14px;right:14px;bottom:14px}}
</style>
</head>
<body>

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-brain" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></symbol>
  <symbol id="i-folder" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></symbol>
  <symbol id="i-folders" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/><path d="M15 4h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5"/><path d="M12 2v20"/></symbol>
  <symbol id="i-file" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></symbol>
  <symbol id="i-layers" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></symbol>
  <symbol id="i-gauge" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></symbol>
  <symbol id="i-bolt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></symbol>
  <symbol id="i-db" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></symbol>
  <symbol id="i-code" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></symbol>
  <symbol id="i-filter" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></symbol>
  <symbol id="i-sliders" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></symbol>
  <symbol id="i-play" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></symbol>
  <symbol id="i-pause" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="10" y1="15" x2="10" y2="9"/><line x1="14" y1="15" x2="14" y2="9"/></symbol>
  <symbol id="i-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></symbol>
  <symbol id="i-fire" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></symbol>
  <symbol id="i-rotate" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></symbol>
  <symbol id="i-save" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></symbol>
  <symbol id="i-reset" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></symbol>
  <symbol id="i-inbox" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></symbol>
</svg>

<main class="shell">
  <header class="hero">
    <div class="brand">
      <div class="logo"><svg><use href="#i-brain"/></svg></div>
      <div>
        <h1>J.A.R.V.I.S</h1>
        <p>Knowledge Indexer</p>
      </div>
    </div>
    <div id="state-badge" class="pill idle"><span id="state-text">Loading</span></div>
  </header>

  <section class="stats">
    <div class="stat">
      <div class="ic"><svg><use href="#i-folders"/></svg></div>
      <div><div class="val" id="stat-folders">0</div><div class="lb">Folders</div></div>
    </div>
    <div class="stat">
      <div class="ic"><svg><use href="#i-file"/></svg></div>
      <div><div class="val" id="stat-files">0 / 0</div><div class="lb">Files Indexed</div></div>
    </div>
    <div class="stat p">
      <div class="ic"><svg><use href="#i-layers"/></svg></div>
      <div><div class="val" id="stat-chunks">0</div><div class="lb">Chunks Stored</div></div>
    </div>
    <div class="stat s">
      <div class="ic"><svg><use href="#i-gauge"/></svg></div>
      <div><div class="val" id="stat-progress">0%</div><div class="lb">Progress</div></div>
    </div>
  </section>

  <div class="prog">
    <div class="prog-head">
      <div class="l"><svg width="11" height="11" style="vertical-align:-1px;margin-right:6px"><use href="#i-bolt"/></svg>Indexing Progress</div>
      <div class="d" id="progress-text">Idle</div>
    </div>
    <div class="track"><div class="fill" id="progress-fill"></div></div>
  </div>

  <div class="tabs">
    <button class="tab on" data-tab="tab-folders"><svg><use href="#i-folder"/></svg><span>Folders</span></button>
    <button class="tab" data-tab="tab-filters"><svg><use href="#i-sliders"/></svg><span>Filters</span></button>
    <button class="tab" data-tab="tab-actions"><svg><use href="#i-shield"/></svg><span>Actions</span></button>
  </div>

  <div id="tab-folders" class="tab-pane on">
    <div class="card">
      <h2><svg><use href="#i-plus"/></svg>Add Folder</h2>
      <div class="row">
        <input type="text" id="add-folder-input" placeholder="Full path to folder (e.g., D:/Projects)">
        <button class="pri" onclick="addFolder()"><svg><use href="#i-bolt"/></svg>Add &amp; Index</button>
      </div>
      <div class="hint">System folders and sensitive paths are automatically blocked.</div>
    </div>
    <div class="card">
      <h2><svg><use href="#i-db"/></svg>Indexed Folders<span class="badge" id="folder-badge">0</span></h2>
      <div id="folders-list"></div>
    </div>
  </div>

  <div id="tab-filters" class="tab-pane">
    <div class="card">
      <h2><svg><use href="#i-code"/></svg>File Extensions</h2>
      <div class="g2">
        <div class="field">
          <label>Include Extensions</label>
          <textarea id="f-include" rows="6"></textarea>
          <div class="hint">One per line. Files with these extensions will be indexed.</div>
        </div>
        <div class="field">
          <label>Exclude Extensions</label>
          <textarea id="f-exclude" rows="6"></textarea>
          <div class="hint">One per line. Files with these extensions will be skipped.</div>
        </div>
      </div>
    </div>
    <div class="card">
      <h2><svg><use href="#i-filter"/></svg>Folder Exclusion</h2>
      <div class="g2">
        <div class="field">
          <label>Skip Folder Names</label>
          <textarea id="f-folders" rows="5"></textarea>
          <div class="hint">Folders with these names will be skipped entirely.</div>
        </div>
        <div class="field">
          <label>Custom Ignore Patterns</label>
          <textarea id="f-patterns" rows="5"></textarea>
          <div class="hint">Glob patterns (e.g., *.tmp, backup_*) to skip.</div>
        </div>
      </div>
    </div>
    <div class="card">
      <h2><svg><use href="#i-gauge"/></svg>Limits &amp; Toggles</h2>
      <div class="g4">
        <div class="field"><label>Max File Size (MB)</label><input type="number" id="f-max-size" min="1" max="100"></div>
        <div class="field"><label>Max Depth</label><input type="number" id="f-max-depth" min="1" max="30"></div>
        <div class="field"><label>Skip Hidden</label><input type="text" id="f-skip-hidden" placeholder="true / false"></div>
        <div class="field"><label>Skip Symlinks</label><input type="text" id="f-skip-symlinks" placeholder="true / false"></div>
      </div>
    </div>
    <div class="card">
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="pri" onclick="saveFilters()"><svg><use href="#i-save"/></svg>Save Filters</button>
        <button class="gho" onclick="resetFilters()"><svg><use href="#i-reset"/></svg>Reset Defaults</button>
      </div>
      <div class="hint" style="margin-top:10px">Saving filters only affects future indexing. Re-index folders to apply new rules.</div>
    </div>
  </div>

  <div id="tab-actions" class="tab-pane">
    <div class="card">
      <h2><svg><use href="#i-play"/></svg>Indexing Control</h2>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="wrn" onclick="pauseIndex()"><svg><use href="#i-pause"/></svg>Pause Indexing</button>
        <button class="pri" onclick="resumeIndex()"><svg><use href="#i-play"/></svg>Resume Indexing</button>
      </div>
    </div>
    <div class="card">
      <h2 style="color:var(--err)"><svg style="color:var(--err)"><use href="#i-alert"/></svg>Danger Zone</h2>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="dgr" onclick="purgeAll()"><svg><use href="#i-fire"/></svg>Purge Entire Index</button>
      </div>
      <div class="hint" style="margin-top:10px">This removes all indexed content from the vector database. Folders remain registered.</div>
    </div>
  </div>
</main>

<div class="toast" id="toast"><span id="toast-msg">Notification</span></div>

<script>
let toastTimer=null, folderPaths=[];
function escapeHtml(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function showToast(msg,isErr){
  const t=document.getElementById('toast');
  document.getElementById('toast-msg').textContent=msg;
  t.className='toast on'+(isErr?' err':'');
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>{t.className='toast';},3200);
}
document.querySelectorAll('.tab').forEach(b=>{
  b.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
    document.querySelectorAll('.tab-pane').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    document.getElementById(b.dataset.tab).classList.add('on');
  });
});
async function api(p,m,b){
  const o={method:m||'GET',headers:{'Content-Type':'application/json'}};
  if(b)o.body=JSON.stringify(b);
  const r=await fetch(p,o);
  return await r.json();
}
async function refreshStatus(){
  try{
    const d=await api('/api/status');
    const p=d.progress;
    const badge=document.getElementById('state-badge');
    const st=(p.state||'idle').toLowerCase();
    badge.className='pill '+st;
    document.getElementById('state-text').textContent=st;
    document.getElementById('stat-folders').textContent=d.folders.length;
    document.getElementById('stat-files').textContent=p.files_done+' / '+p.files_total;
    document.getElementById('stat-chunks').textContent=p.chunks_done;
    document.getElementById('stat-progress').textContent=p.percent.toFixed(1)+'%';
    document.getElementById('progress-fill').style.width=p.percent+'%';
    let txt='Idle — waiting for changes';
    if(p.state==='scanning')txt='Scanning: '+(p.current_folder||'...');
    else if(p.state==='paused')txt='Paused';
    else if(p.state==='error')txt='Error: '+(p.last_error||'unknown');
    else if(p.last_completed)txt='Last completed: '+p.last_completed;
    document.getElementById('progress-text').textContent=txt;
    renderFolders(d.folders);
  }catch(e){console.error('Status refresh failed',e);}
}
function renderFolders(folders){
  folderPaths=folders.map(f=>f.path);
  document.getElementById('folder-badge').textContent=folders.length;
  const list=document.getElementById('folders-list');
  if(!folders||folders.length===0){
    list.innerHTML='<div class="empty">No folders indexed yet. Add a folder to begin.</div>';
    return;
  }
  const BS=String.fromCharCode(92);
  list.innerHTML=folders.map((f,i)=>{
    const norm=f.path.split(BS).join('/');
    const name=norm.split('/').pop()||f.path;
    const tag=f.is_default?'<span class="tag">default</span>':'';
    return '<div class="folder" data-index="'+i+'">'+
      '<div class="fi"><svg><use href="#i-folder"/></svg></div>'+
      '<div class="inf">'+
        '<div class="nm">'+escapeHtml(name)+tag+'</div>'+
        '<div class="meta"><span>'+f.file_count+' files</span><span>'+f.chunk_count+' chunks</span></div>'+
        '<div class="path" title="'+escapeHtml(f.path)+'">'+escapeHtml(f.path)+'</div>'+
      '</div>'+
      '<div class="acts">'+
        '<button class="icon-btn acc" data-action="reindex" data-index="'+i+'" title="Reindex"><svg><use href="#i-rotate"/></svg></button>'+
        '<button class="icon-btn dgr" data-action="remove" data-index="'+i+'" title="Remove"><svg><use href="#i-x"/></svg></button>'+
      '</div>'+
    '</div>';
  }).join('');
  list.querySelectorAll('[data-action]').forEach(btn=>{
    btn.addEventListener('click',()=>{
      const idx=parseInt(btn.dataset.index,10);
      const path=folderPaths[idx];
      if(btn.dataset.action==='remove')removeFolder(path);
      else if(btn.dataset.action==='reindex')reindexFolder(path);
    });
  });
}
async function addFolder(){
  const input=document.getElementById('add-folder-input');
  const path=input.value.trim();
  if(!path)return showToast('Enter a folder path',true);
  const r=await api('/api/folders/add','POST',{path});
  if(r.success){showToast('Folder added. Indexing started.');input.value='';refreshStatus();}
  else showToast(r.error||'Failed to add folder',true);
}
async function removeFolder(path){
  if(!confirm('Remove this folder from index?'))return;
  const r=await api('/api/folders/remove','POST',{path});
  if(r.success){showToast('Folder removed.');refreshStatus();}
  else showToast(r.error||'Failed to remove folder',true);
}
async function reindexFolder(path){
  const r=await api('/api/folders/reindex','POST',{path});
  if(r.success)showToast('Reindex started in background.');
  else showToast(r.error||'Reindex failed',true);
  refreshStatus();
}
async function loadFilters(){
  try{
    const f=await api('/api/filters');
    document.getElementById('f-include').value=(f.include_extensions||[]).join('\\n');
    document.getElementById('f-exclude').value=(f.exclude_extensions||[]).join('\\n');
    document.getElementById('f-folders').value=(f.exclude_folders||[]).join('\\n');
    document.getElementById('f-patterns').value=(f.custom_ignore_patterns||[]).join('\\n');
    document.getElementById('f-max-size').value=f.max_file_size_mb||5;
    document.getElementById('f-max-depth').value=f.max_depth||15;
    document.getElementById('f-skip-hidden').value=String(f.skip_hidden);
    document.getElementById('f-skip-symlinks').value=String(f.skip_symlinks);
  }catch(e){console.error('Load filters failed',e);}
}
function parseLines(id){return document.getElementById(id).value.split('\\n').map(x=>x.trim()).filter(x=>x);}
async function saveFilters(){
  const payload={
    include_extensions:parseLines('f-include'),
    exclude_extensions:parseLines('f-exclude'),
    exclude_folders:parseLines('f-folders'),
    custom_ignore_patterns:parseLines('f-patterns'),
    max_file_size_mb:parseInt(document.getElementById('f-max-size').value,10)||5,
    max_depth:parseInt(document.getElementById('f-max-depth').value,10)||15,
    skip_hidden:document.getElementById('f-skip-hidden').value.toLowerCase()==='true',
    skip_symlinks:document.getElementById('f-skip-symlinks').value.toLowerCase()==='true'
  };
  const r=await api('/api/filters','POST',payload);
  if(r.success)showToast('Filters saved.');else showToast(r.error||'Save failed',true);
}
async function resetFilters(){
  if(!confirm('Reset all filters to defaults?'))return;
  const r=await api('/api/filters/reset','POST',{});
  if(r.success){showToast('Filters reset to defaults.');loadFilters();}
  else showToast(r.error||'Reset failed',true);
}
async function pauseIndex(){
  const r=await api('/api/pause','POST',{});
  if(r.success)showToast('Indexing paused.');
  refreshStatus();
}
async function resumeIndex(){
  const r=await api('/api/resume','POST',{});
  if(r.success)showToast('Indexing resumed.');
  refreshStatus();
}
async function purgeAll(){
  if(!confirm('PURGE ENTIRE INDEX? This cannot be undone.'))return;
  const r=await api('/api/purge/all','POST',{});
  if(r.success){showToast('Index purged.');refreshStatus();}
  else showToast(r.error||'Purge failed',true);
}
refreshStatus();
loadFilters();
setInterval(refreshStatus,2500);
</script>
</body>
</html>"""


def find_free_port(start=8080, end=8095):
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def create_app():
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route("/api/status")
    def api_status():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify({
                "progress": rag_engine.get_progress(),
                "folders": rag_engine.list_folders(),
                "summary": rag_engine.get_indexed_folders_summary()
            })
        except Exception as e:
            logger.error(f"Dashboard api_status failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/folders")
    def api_folders():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify({"folders": rag_engine.list_folders()})
        except Exception as e:
            logger.error(f"Dashboard api_folders failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/folders/add", methods=["POST"])
    def api_folder_add():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400
            from core.brain.RagEngine import rag_engine
            result = rag_engine.add_folder(path)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_folder_add failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/folders/remove", methods=["POST"])
    def api_folder_remove():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400
            from core.brain.RagEngine import rag_engine
            result = rag_engine.remove_folder(path)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_folder_remove failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/folders/reindex", methods=["POST"])
    def api_folder_reindex():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400

            from pathlib import Path
            import os
            try:
                resolved = str(Path(path).expanduser().resolve())
            except Exception:
                return jsonify({"success": False, "error": "Invalid path."}), 400

            if not os.path.isdir(resolved):
                return jsonify({"success": False, "error": "Folder does not exist."}), 400

            from core.brain.Indexer.config_store import config_store
            folders = config_store.load_folders()
            registered = any(f["path"] == resolved for f in folders)
            if not registered:
                return jsonify({"success": False, "error": "Folder not registered."}), 400

            from core.brain.RagEngine import rag_engine
            threading.Thread(
                target=rag_engine.reindex_folder,
                args=(resolved,),
                daemon=True
            ).start()

            return jsonify({"success": True, "path": resolved, "message": "Reindex started in background."})
        except Exception as e:
            logger.error(f"Dashboard api_folder_reindex failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/filters")
    def api_filters_get():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.get_filters())
        except Exception as e:
            logger.error(f"Dashboard api_filters_get failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/filters", methods=["POST"])
    def api_filters_post():
        try:
            data = request.get_json() or {}
            from core.brain.RagEngine import rag_engine
            result = rag_engine.update_filters(data)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_filters_post failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/filters/reset", methods=["POST"])
    def api_filters_reset():
        try:
            from core.brain.Indexer.config_store import config_store
            from core.brain.RagEngine import rag_engine
            config_store.reset_filters()
            new_filters = config_store.load_filters()
            rag_engine.filter_engine.reload(new_filters)
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Dashboard api_filters_reset failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pause", methods=["POST"])
    def api_pause():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.pause_indexing())
        except Exception as e:
            logger.error(f"Dashboard api_pause failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/resume", methods=["POST"])
    def api_resume():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.resume_indexing())
        except Exception as e:
            logger.error(f"Dashboard api_resume failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/purge/all", methods=["POST"])
    def api_purge_all():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.purge_all())
        except Exception as e:
            logger.error(f"Dashboard api_purge_all failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    return app


def start_dashboard(port=None):
    global _flask_app, _server, _server_thread, _actual_port

    with _dashboard_lock:
        if _server is not None:
            logger.info(f"Dashboard already running on port {_actual_port}.")
            return _actual_port

        _flask_app = create_app()

        if port is None:
            port = find_free_port()

        if port is None:
            logger.error("Dashboard: no free port found in range 8080-8095.")
            return None

        try:
            if WERKZEUG_OK:
                _server = make_server("127.0.0.1", port, _flask_app, threaded=True)
                _server_thread = threading.Thread(
                    target=_server.serve_forever,
                    name="JarvisDashboard",
                    daemon=True
                )
                _server_thread.start()
            else:
                _server_thread = threading.Thread(
                    target=_flask_app.run,
                    kwargs={
                        "host": "127.0.0.1",
                        "port": port,
                        "debug": False,
                        "use_reloader": False,
                        "threaded": True
                    },
                    name="JarvisDashboard",
                    daemon=True
                )
                _server_thread.start()
                time.sleep(1)

            _actual_port = port
            logger.info(f"Indexer Dashboard running at http://127.0.0.1:{port}")
            return port
        except Exception as e:
            logger.error(f"Dashboard start failed: {e}")
            _server = None
            _server_thread = None
            return None


def stop_dashboard():
    global _server, _server_thread, _actual_port

    with _dashboard_lock:
        if _server is not None:
            try:
                _server.shutdown()
            except Exception as e:
                logger.warning(f"Dashboard shutdown warning: {e}")
            _server = None

        if _server_thread is not None:
            try:
                _server_thread.join(timeout=3)
            except Exception as e:
                logger.warning(f"Dashboard thread join warning: {e}")
            _server_thread = None

        _actual_port = None
        logger.info("Indexer Dashboard stopped.")


def is_dashboard_running():
    return (
        _server_thread is not None
        and _server_thread.is_alive()
    )


def get_dashboard_port():
    return _actual_port


if __name__ == "__main__":
    import sys
    from pathlib import Path

    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    port = start_dashboard()
    if port:
        logger.info(f"Standalone dashboard running on port {port}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_dashboard()
    else:
        logger.error("Failed to start standalone dashboard.")