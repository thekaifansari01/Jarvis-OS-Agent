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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Orbitron:wght@500;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
<style>
:root {
    --bg-0: #030711;
    --bg-1: #0a0f24;
    --bg-2: #111a35;
    --surface: rgba(15, 23, 42, 0.55);
    --surface-2: rgba(30, 41, 59, 0.65);
    --border: rgba(148, 163, 184, 0.14);
    --border-hover: rgba(56, 189, 248, 0.45);
    --accent: #38bdf8;
    --accent-2: #22d3ee;
    --accent-3: #a855f7;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --muted-2: #64748b;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html, body { min-height: 100%; }

body {
    min-height: 100vh;
    font-family: 'Inter', system-ui, sans-serif;
    background: var(--bg-0);
    color: var(--text);
    overflow-x: hidden;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding: 32px 20px;
    position: relative;
}

.bg-orbs {
    position: fixed;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
}

.orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(90px);
    opacity: 0.5;
    will-change: transform;
}

.orb-1 {
    width: 520px; height: 520px;
    background: radial-gradient(circle, #0ea5e9, transparent 65%);
    top: -180px; left: -140px;
    animation: float1 22s ease-in-out infinite;
}

.orb-2 {
    width: 620px; height: 620px;
    background: radial-gradient(circle, #a855f7, transparent 65%);
    bottom: -220px; right: -180px;
    animation: float2 26s ease-in-out infinite;
}

.orb-3 {
    width: 400px; height: 400px;
    background: radial-gradient(circle, #06b6d4, transparent 65%);
    top: 40%; left: 45%;
    animation: float3 30s ease-in-out infinite;
    opacity: 0.28;
}

@keyframes float1 {
    0%, 100% { transform: translate(0, 0) scale(1); }
    50%      { transform: translate(90px, 70px) scale(1.12); }
}
@keyframes float2 {
    0%, 100% { transform: translate(0, 0) scale(1); }
    50%      { transform: translate(-100px, -80px) scale(1.15); }
}
@keyframes float3 {
    0%, 100% { transform: translate(0, 0) scale(1); }
    33%      { transform: translate(-70px, 50px) scale(1.08); }
    66%      { transform: translate(80px, -60px) scale(0.94); }
}

.shell {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 1180px;
    background: linear-gradient(160deg, rgba(15,23,42,0.72), rgba(2,6,23,0.85));
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border-radius: 24px;
    border: 1px solid var(--border);
    box-shadow:
        0 30px 80px rgba(0, 0, 0, 0.55),
        0 0 0 1px rgba(56, 189, 248, 0.05),
        inset 0 1px 0 rgba(255, 255, 255, 0.06);
    padding: 34px;
    animation: shellIn 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes shellIn {
    from { opacity: 0; transform: translateY(28px) scale(0.985); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}

.hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
    flex-wrap: wrap;
}

.brand {
    display: flex;
    align-items: center;
    gap: 16px;
}

.logo {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    font-size: 22px;
    color: #e0f2fe;
    background: linear-gradient(135deg, #0ea5e9, #6366f1, #a855f7);
    box-shadow: 0 0 30px rgba(56, 189, 248, 0.55), inset 0 1px 0 rgba(255,255,255,0.3);
    animation: logoPulse 3.6s ease-in-out infinite;
}

@keyframes logoPulse {
    0%, 100% { box-shadow: 0 0 30px rgba(56, 189, 248, 0.55), inset 0 1px 0 rgba(255,255,255,0.3); }
    50%      { box-shadow: 0 0 50px rgba(168, 85, 247, 0.75), inset 0 1px 0 rgba(255,255,255,0.35); }
}

.brand h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 6px;
    color: #f0f9ff;
    text-shadow: 0 0 24px rgba(56, 189, 248, 0.65);
}

.brand p {
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 3px;
    margin-top: 4px;
    text-transform: uppercase;
}

.status-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 18px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    transition: all 0.3s;
    border: 1px solid;
}

.status-pill .pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    box-shadow: 0 0 0 0 currentColor;
    animation: pillPulse 1.8s infinite;
}

@keyframes pillPulse {
    0%   { box-shadow: 0 0 0 0 currentColor; }
    70%  { box-shadow: 0 0 0 10px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
}

.status-pill.idle { background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.35); color: var(--success); }
.status-pill.scanning { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.35); color: var(--warning); }
.status-pill.paused { background: rgba(148,163,184,0.08); border-color: rgba(148,163,184,0.35); color: var(--muted); }
.status-pill.error { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.35); color: var(--danger); }

.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 20px;
}

.stat {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 16px 18px;
    border-radius: 14px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.stat:hover {
    border-color: var(--border-hover);
    transform: translateY(-3px);
    box-shadow: 0 14px 34px rgba(56, 189, 248, 0.15);
}

.stat i {
    font-size: 18px;
    color: var(--accent);
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    background: rgba(56, 189, 248, 0.08);
    border: 1px solid rgba(56, 189, 248, 0.2);
    flex-shrink: 0;
}

.stat.accent-2 i { color: var(--accent-3); background: rgba(168,85,247,0.08); border-color: rgba(168,85,247,0.2); }
.stat.success i { color: var(--success); background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.2); }

.stat > div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.stat span {
    font-size: 20px;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: 0.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.stat small {
    font-size: 10.5px;
    color: var(--muted);
    letter-spacing: 1.4px;
    text-transform: uppercase;
    font-weight: 600;
}

.progress-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 24px;
    transition: border-color 0.3s;
}

.progress-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}

.progress-head .label {
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
}

.progress-head .label i { color: var(--accent); }

.progress-head .detail {
    font-size: 12px;
    color: var(--muted);
    font-family: 'Inter', monospace;
    letter-spacing: 0.5px;
}

.progress-track {
    background: rgba(2, 6, 23, 0.7);
    height: 10px;
    border-radius: 5px;
    overflow: hidden;
    position: relative;
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
}

.progress-fill {
    background: linear-gradient(90deg, #38bdf8, #22d3ee, #a855f7, #38bdf8);
    background-size: 300% 100%;
    height: 100%;
    width: 0%;
    border-radius: 5px;
    transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    animation: shimmer 3s linear infinite;
    box-shadow: 0 0 20px rgba(56, 189, 248, 0.6);
}

@keyframes shimmer {
    0%   { background-position: 0% 50%; }
    100% { background-position: 300% 50%; }
}

.tabs {
    display: flex;
    gap: 6px;
    padding: 6px;
    background: rgba(2, 6, 23, 0.5);
    border-radius: 12px;
    border: 1px solid var(--border);
    margin-bottom: 22px;
    width: fit-content;
    max-width: 100%;
    overflow-x: auto;
}

.tab {
    padding: 10px 22px;
    cursor: pointer;
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    border-radius: 8px;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
    font-family: inherit;
}

.tab:hover { color: var(--text); }

.tab.active {
    color: #e0f2fe;
    background: linear-gradient(135deg, rgba(56,189,248,0.18), rgba(168,85,247,0.18));
    box-shadow: 0 0 18px rgba(56, 189, 248, 0.25), inset 0 1px 0 rgba(255,255,255,0.08);
}

.tab i { font-size: 12px; }

.tab-content { display: none; animation: fadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1); }
.tab-content.active { display: block; }

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

.card {
    position: relative;
    border-radius: 18px;
    padding: 22px;
    background: linear-gradient(160deg, rgba(30,41,59,0.5), rgba(2,6,23,0.7));
    border: 1px solid var(--border);
    margin-bottom: 18px;
    overflow: hidden;
    transition: border-color 0.35s;
}

.card::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 18px;
    padding: 1px;
    background: linear-gradient(135deg, transparent 40%, rgba(56,189,248,0.35) 50%, transparent 60%);
    background-size: 300% 300%;
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    opacity: 0;
    transition: opacity 0.4s;
    pointer-events: none;
}

.card:hover::after {
    opacity: 1;
    animation: borderShift 3s linear infinite;
}

@keyframes borderShift {
    0%   { background-position: 0% 0%; }
    100% { background-position: 300% 300%; }
}

.card-head {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2.4px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 18px;
}

.card-head i { color: var(--accent); font-size: 13px; }

.card-head .badge {
    margin-left: auto;
    background: rgba(56, 189, 248, 0.12);
    border: 1px solid rgba(56, 189, 248, 0.35);
    color: var(--accent);
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
}

button {
    font-family: inherit;
    cursor: pointer;
    border-radius: 10px;
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: 0.3px;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--text);
    padding: 10px 18px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    justify-content: center;
}

button:hover { border-color: var(--border-hover); background: rgba(56,189,248,0.1); }
button:disabled { opacity: 0.4; cursor: not-allowed; }

button.primary {
    background: linear-gradient(135deg, #0ea5e9, #6366f1);
    border-color: rgba(56, 189, 248, 0.5);
    color: white;
    box-shadow: 0 0 20px rgba(56, 189, 248, 0.35);
}
button.primary:hover {
    box-shadow: 0 0 30px rgba(56, 189, 248, 0.6);
    transform: translateY(-1px);
}

button.danger {
    background: linear-gradient(135deg, #dc2626, #ef4444);
    border-color: rgba(239, 68, 68, 0.5);
    color: white;
    box-shadow: 0 0 20px rgba(239, 68, 68, 0.25);
}
button.danger:hover {
    box-shadow: 0 0 30px rgba(239, 68, 68, 0.55);
    transform: translateY(-1px);
}

button.ghost {
    background: transparent;
    border-color: var(--border);
}

button.warning {
    background: linear-gradient(135deg, #d97706, #f59e0b);
    border-color: rgba(245, 158, 11, 0.5);
    color: white;
    box-shadow: 0 0 20px rgba(245, 158, 11, 0.25);
}
button.warning:hover { box-shadow: 0 0 30px rgba(245, 158, 11, 0.5); }

.btn-icon {
    width: 38px;
    height: 38px;
    padding: 0;
    border-radius: 10px;
    font-size: 13px;
}

.btn-icon.danger {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: var(--danger);
    box-shadow: none;
}
.btn-icon.danger:hover {
    background: var(--danger);
    color: white;
    border-color: var(--danger);
    box-shadow: 0 0 20px rgba(239, 68, 68, 0.6);
    transform: scale(1.08);
}

.btn-icon:not(.danger) {
    background: rgba(56, 189, 248, 0.08);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: var(--accent);
    box-shadow: none;
}
.btn-icon:not(.danger):hover {
    background: var(--accent);
    color: #0a0f24;
    border-color: var(--accent);
    box-shadow: 0 0 20px rgba(56, 189, 248, 0.6);
    transform: scale(1.08);
}

input[type="text"], input[type="number"], textarea {
    background: rgba(2, 6, 23, 0.7);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 13px;
    font-family: inherit;
    width: 100%;
    transition: all 0.2s;
}

input:focus, textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

textarea {
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
    resize: vertical;
    line-height: 1.6;
}

.form-row {
    display: flex;
    gap: 10px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.form-row input { flex: 1; min-width: 200px; }

.field { margin-bottom: 16px; }
.field:last-child { margin-bottom: 0; }

.field label {
    display: block;
    font-size: 11.5px;
    color: var(--muted);
    margin-bottom: 8px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    font-weight: 700;
}

.field-hint {
    font-size: 11px;
    color: var(--muted-2);
    margin-top: 6px;
    line-height: 1.5;
}

.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }

.folder-row {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 16px;
    background: linear-gradient(145deg, rgba(30,41,59,0.7), rgba(15,23,42,0.85));
    border: 1px solid var(--border);
    border-radius: 14px;
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
    animation: slideIn 0.45s cubic-bezier(0.16, 1, 0.3, 1);
    transition: border-color 0.3s, transform 0.3s, box-shadow 0.3s;
}

.folder-row::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--accent), var(--accent-3));
    opacity: 0;
    transition: opacity 0.3s;
}

.folder-row:hover {
    border-color: rgba(56, 189, 248, 0.4);
    transform: translateX(4px);
    box-shadow: 0 10px 30px rgba(56, 189, 248, 0.12);
}

.folder-row:hover::before { opacity: 1; }

@keyframes slideIn {
    from { opacity: 0; transform: translateX(-28px); }
    to   { opacity: 1; transform: translateX(0); }
}

.folder-icon {
    width: 42px;
    height: 42px;
    border-radius: 11px;
    display: grid;
    place-items: center;
    font-size: 16px;
    color: #fbbf24;
    background: linear-gradient(135deg, rgba(56,189,248,0.18), rgba(168,85,247,0.18));
    border: 1px solid rgba(56, 189, 248, 0.28);
    flex-shrink: 0;
}

.folder-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.folder-name {
    font-size: 14px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: 0.3px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}

.tag-default {
    font-size: 9.5px;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: var(--accent);
    letter-spacing: 1px;
    text-transform: uppercase;
    font-weight: 800;
}

.folder-meta {
    display: flex;
    gap: 14px;
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 0.5px;
    font-weight: 600;
}

.folder-meta span {
    display: flex;
    align-items: center;
    gap: 5px;
}

.folder-meta i { font-size: 10px; color: var(--accent); }

.folder-path {
    font-size: 11px;
    color: var(--muted-2);
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    letter-spacing: 0.3px;
}

.folder-actions { display: flex; gap: 8px; flex-shrink: 0; }

.empty-state {
    text-align: center;
    padding: 46px 20px;
    color: var(--muted);
    border: 1px dashed var(--border);
    border-radius: 14px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
}

.empty-state i {
    font-size: 28px;
    color: var(--muted-2);
    animation: softFloat 3s ease-in-out infinite;
}

@keyframes softFloat {
    0%, 100% { transform: translateY(0); opacity: 0.7; }
    50%      { transform: translateY(-6px); opacity: 1; }
}

.empty-state p {
    font-size: 12.5px;
    letter-spacing: 0.6px;
}

.toast {
    position: fixed;
    bottom: 30px;
    right: 30px;
    padding: 14px 22px;
    background: linear-gradient(135deg, #10b981, #22d3ee);
    color: white;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.3px;
    opacity: 0;
    transform: translateY(20px);
    transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 20px 50px rgba(16, 185, 129, 0.4);
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 380px;
}

.toast.show { opacity: 1; transform: translateY(0); }
.toast.error {
    background: linear-gradient(135deg, #dc2626, #ef4444);
    box-shadow: 0 20px 50px rgba(239, 68, 68, 0.4);
}

.toast i { font-size: 15px; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: rgba(2, 6, 23, 0.4); border-radius: 4px; }
::-webkit-scrollbar-thumb {
    background: rgba(56, 189, 248, 0.25);
    border-radius: 4px;
    transition: background 0.2s;
}
::-webkit-scrollbar-thumb:hover { background: rgba(56, 189, 248, 0.5); }

@media (max-width: 900px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .grid-2 { grid-template-columns: 1fr; }
    .grid-4 { grid-template-columns: repeat(2, 1fr); }
    .shell { padding: 24px; }
}

@media (max-width: 560px) {
    body { padding: 16px 12px; }
    .stats { grid-template-columns: 1fr; }
    .hero { flex-direction: column; align-items: flex-start; }
    .brand h1 { font-size: 18px; letter-spacing: 4px; }
    .tab { padding: 9px 14px; font-size: 11px; }
    .tab span { display: none; }
    .toast { left: 16px; right: 16px; bottom: 16px; }
}
</style>
</head>
<body>
<div class="bg-orbs">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
</div>

<main class="shell">
    <header class="hero">
        <div class="brand">
            <div class="logo"><i class="fa-solid fa-brain"></i></div>
            <div>
                <h1>J.A.R.V.I.S</h1>
                <p>Knowledge Indexer</p>
            </div>
        </div>
        <div id="state-badge" class="status-pill idle">
            <span class="pulse"></span>
            <span id="state-text">Loading</span>
        </div>
    </header>

    <section class="stats">
        <div class="stat">
            <i class="fa-solid fa-folder-tree"></i>
            <div>
                <span id="stat-folders">0</span>
                <small>Folders</small>
            </div>
        </div>
        <div class="stat">
            <i class="fa-solid fa-file-lines"></i>
            <div>
                <span id="stat-files">0 / 0</span>
                <small>Files Indexed</small>
            </div>
        </div>
        <div class="stat accent-2">
            <i class="fa-solid fa-layer-group"></i>
            <div>
                <span id="stat-chunks">0</span>
                <small>Chunks Stored</small>
            </div>
        </div>
        <div class="stat success">
            <i class="fa-solid fa-gauge-high"></i>
            <div>
                <span id="stat-progress">0%</span>
                <small>Progress</small>
            </div>
        </div>
    </section>

    <div class="progress-card">
        <div class="progress-head">
            <div class="label"><i class="fa-solid fa-bolt"></i> Indexing Progress</div>
            <div class="detail" id="progress-text">Idle</div>
        </div>
        <div class="progress-track">
            <div class="progress-fill" id="progress-fill"></div>
        </div>
    </div>

    <div class="tabs">
        <button class="tab active" data-tab="tab-folders">
            <i class="fa-solid fa-folder-open"></i><span>Folders</span>
        </button>
        <button class="tab" data-tab="tab-filters">
            <i class="fa-solid fa-sliders"></i><span>Filters</span>
        </button>
        <button class="tab" data-tab="tab-actions">
            <i class="fa-solid fa-shield-halved"></i><span>Actions</span>
        </button>
    </div>

    <div id="tab-folders" class="tab-content active">
        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-plus"></i>
                <span>Add Folder</span>
            </div>
            <div class="form-row">
                <input type="text" id="add-folder-input" placeholder="Full path to folder (e.g., D:/Projects)">
                <button class="primary" onclick="addFolder()">
                    <i class="fa-solid fa-bolt"></i> Add & Index
                </button>
            </div>
            <div class="field-hint">System folders and sensitive paths are automatically blocked or flagged.</div>
        </div>

        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-database"></i>
                <span>Indexed Folders</span>
                <span class="badge" id="folder-badge">0</span>
            </div>
            <div id="folders-list"></div>
        </div>
    </div>

    <div id="tab-filters" class="tab-content">
        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-file-code"></i>
                <span>File Extensions</span>
            </div>
            <div class="grid-2">
                <div class="field">
                    <label>Include Extensions</label>
                    <textarea id="f-include" rows="6"></textarea>
                    <div class="field-hint">One per line. Files with these extensions will be indexed.</div>
                </div>
                <div class="field">
                    <label>Exclude Extensions</label>
                    <textarea id="f-exclude" rows="6"></textarea>
                    <div class="field-hint">One per line. Files with these extensions will be skipped.</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-filter-circle-xmark"></i>
                <span>Folder Exclusion</span>
            </div>
            <div class="grid-2">
                <div class="field">
                    <label>Skip Folder Names</label>
                    <textarea id="f-folders" rows="5"></textarea>
                    <div class="field-hint">Folders with these names will be skipped entirely.</div>
                </div>
                <div class="field">
                    <label>Custom Ignore Patterns</label>
                    <textarea id="f-patterns" rows="5"></textarea>
                    <div class="field-hint">Glob patterns (e.g., *.tmp, backup_*) to skip.</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-gauge-simple-high"></i>
                <span>Limits & Toggles</span>
            </div>
            <div class="grid-4">
                <div class="field">
                    <label>Max File Size (MB)</label>
                    <input type="number" id="f-max-size" min="1" max="100">
                </div>
                <div class="field">
                    <label>Max Depth</label>
                    <input type="number" id="f-max-depth" min="1" max="30">
                </div>
                <div class="field">
                    <label>Skip Hidden</label>
                    <input type="text" id="f-skip-hidden" placeholder="true / false">
                </div>
                <div class="field">
                    <label>Skip Symlinks</label>
                    <input type="text" id="f-skip-symlinks" placeholder="true / false">
                </div>
            </div>
        </div>

        <div class="card">
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
                <button class="primary" onclick="saveFilters()">
                    <i class="fa-solid fa-floppy-disk"></i> Save Filters
                </button>
                <button class="ghost" onclick="resetFilters()">
                    <i class="fa-solid fa-rotate-left"></i> Reset Defaults
                </button>
            </div>
            <div class="field-hint" style="margin-top:12px;">Saving filters only affects future indexing. Re-index folders to apply new rules.</div>
        </div>
    </div>

    <div id="tab-actions" class="tab-content">
        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-circle-play"></i>
                <span>Indexing Control</span>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
                <button class="warning" onclick="pauseIndex()">
                    <i class="fa-solid fa-pause"></i> Pause Indexing
                </button>
                <button class="primary" onclick="resumeIndex()">
                    <i class="fa-solid fa-play"></i> Resume Indexing
                </button>
            </div>
        </div>

        <div class="card">
            <div class="card-head">
                <i class="fa-solid fa-triangle-exclamation" style="color:var(--danger);"></i>
                <span>Danger Zone</span>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
                <button class="danger" onclick="purgeAll()">
                    <i class="fa-solid fa-fire"></i> Purge Entire Index
                </button>
            </div>
            <div class="field-hint" style="margin-top:12px;">This removes all indexed content from the vector database. Folders remain registered.</div>
        </div>
    </div>
</main>

<div class="toast" id="toast">
    <i class="fa-solid fa-circle-check"></i>
    <span id="toast-msg">Notification</span>
</div>

<script>
let toastTimer = null;
let folderPaths = [];

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
}

function showToast(msg, isError) {
    const t = document.getElementById('toast');
    const icon = t.querySelector('i');
    const text = document.getElementById('toast-msg');
    text.textContent = msg;
    icon.className = isError ? 'fa-solid fa-circle-exclamation' : 'fa-solid fa-circle-check';
    t.className = 'toast show' + (isError ? ' error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.className = 'toast'; }, 3200);
}

document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(x => x.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(btn.dataset.tab).classList.add('active');
    });
});

async function api(path, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return await res.json();
}

async function refreshStatus() {
    try {
        const d = await api('/api/status');
        const p = d.progress;

        const badge = document.getElementById('state-badge');
        const stateText = document.getElementById('state-text');
        const state = (p.state || 'idle').toLowerCase();
        badge.className = 'status-pill ' + state;
        stateText.textContent = state;

        document.getElementById('stat-folders').textContent = d.folders.length;
        document.getElementById('stat-files').textContent = p.files_done + ' / ' + p.files_total;
        document.getElementById('stat-chunks').textContent = p.chunks_done;
        document.getElementById('stat-progress').textContent = p.percent.toFixed(1) + '%';
        document.getElementById('progress-fill').style.width = p.percent + '%';

        let txt = 'Idle — waiting for changes';
        if (p.state === 'scanning') txt = 'Scanning: ' + (p.current_folder || '...');
        else if (p.state === 'paused') txt = 'Paused';
        else if (p.state === 'error') txt = 'Error: ' + (p.last_error || 'unknown');
        else if (p.last_completed) txt = 'Last completed: ' + p.last_completed;
        document.getElementById('progress-text').textContent = txt;

        renderFolders(d.folders);
    } catch (e) {
        console.error('Status refresh failed', e);
    }
}

function renderFolders(folders) {
    folderPaths = folders.map(f => f.path);
    document.getElementById('folder-badge').textContent = folders.length;

    const list = document.getElementById('folders-list');
    if (!folders || folders.length === 0) {
        list.innerHTML = '<div class="empty-state"><i class="fa-solid fa-inbox"></i><p>No folders indexed yet. Add a folder to begin.</p></div>';
        return;
    }

    const BS = String.fromCharCode(92);

    list.innerHTML = folders.map((f, i) => {
        const norm = f.path.split(BS).join('/');
        const name = norm.split('/').pop() || f.path;
        const defaultTag = f.is_default ? '<span class="tag-default">default</span>' : '';
        return '<div class="folder-row" data-index="' + i + '">' +
            '<div class="folder-icon"><i class="fa-solid fa-folder"></i></div>' +
            '<div class="folder-info">' +
                '<div class="folder-name">' + escapeHtml(name) + defaultTag + '</div>' +
                '<div class="folder-meta">' +
                    '<span><i class="fa-solid fa-file"></i> ' + f.file_count + ' files</span>' +
                    '<span><i class="fa-solid fa-layer-group"></i> ' + f.chunk_count + ' chunks</span>' +
                '</div>' +
                '<div class="folder-path" title="' + escapeHtml(f.path) + '">' + escapeHtml(f.path) + '</div>' +
            '</div>' +
            '<div class="folder-actions">' +
                '<button class="btn-icon" data-action="reindex" data-index="' + i + '" title="Reindex"><i class="fa-solid fa-rotate"></i></button>' +
                '<button class="btn-icon danger" data-action="remove" data-index="' + i + '" title="Remove"><i class="fa-solid fa-trash"></i></button>' +
            '</div>' +
        '</div>';
    }).join('');

    list.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.index, 10);
            const path = folderPaths[idx];
            if (btn.dataset.action === 'remove') removeFolder(path);
            else if (btn.dataset.action === 'reindex') reindexFolder(path);
        });
    });
}

async function addFolder() {
    const input = document.getElementById('add-folder-input');
    const path = input.value.trim();
    if (!path) return showToast('Enter a folder path', true);
    const r = await api('/api/folders/add', 'POST', { path });
    if (r.success) {
        showToast('Folder added. Indexing started.');
        input.value = '';
        refreshStatus();
    } else {
        showToast(r.error || 'Failed to add folder', true);
    }
}

async function removeFolder(path) {
    if (!confirm('Remove this folder from index?')) return;
    const r = await api('/api/folders/remove', 'POST', { path });
    if (r.success) {
        showToast('Folder removed.');
        refreshStatus();
    } else {
        showToast(r.error || 'Failed to remove folder', true);
    }
}

async function reindexFolder(path) {
    showToast('Reindexing started...');
    const r = await api('/api/folders/reindex', 'POST', { path });
    if (r.success) showToast('Reindex complete.');
    else showToast(r.error || 'Reindex failed', true);
    refreshStatus();
}

async function loadFilters() {
    try {
        const f = await api('/api/filters');
        document.getElementById('f-include').value = (f.include_extensions || []).join('\\n');
        document.getElementById('f-exclude').value = (f.exclude_extensions || []).join('\\n');
        document.getElementById('f-folders').value = (f.exclude_folders || []).join('\\n');
        document.getElementById('f-patterns').value = (f.custom_ignore_patterns || []).join('\\n');
        document.getElementById('f-max-size').value = f.max_file_size_mb || 5;
        document.getElementById('f-max-depth').value = f.max_depth || 15;
        document.getElementById('f-skip-hidden').value = String(f.skip_hidden);
        document.getElementById('f-skip-symlinks').value = String(f.skip_symlinks);
    } catch (e) {
        console.error('Load filters failed', e);
    }
}

function parseLines(id) {
    return document.getElementById(id).value.split('\\n').map(x => x.trim()).filter(x => x);
}

async function saveFilters() {
    const payload = {
        include_extensions: parseLines('f-include'),
        exclude_extensions: parseLines('f-exclude'),
        exclude_folders: parseLines('f-folders'),
        custom_ignore_patterns: parseLines('f-patterns'),
        max_file_size_mb: parseInt(document.getElementById('f-max-size').value, 10) || 5,
        max_depth: parseInt(document.getElementById('f-max-depth').value, 10) || 15,
        skip_hidden: document.getElementById('f-skip-hidden').value.toLowerCase() === 'true',
        skip_symlinks: document.getElementById('f-skip-symlinks').value.toLowerCase() === 'true'
    };
    const r = await api('/api/filters', 'POST', payload);
    if (r.success) showToast('Filters saved.');
    else showToast(r.error || 'Save failed', true);
}

async function resetFilters() {
    if (!confirm('Reset all filters to defaults?')) return;
    const r = await api('/api/filters/reset', 'POST', {});
    if (r.success) { showToast('Filters reset to defaults.'); loadFilters(); }
    else showToast(r.error || 'Reset failed', true);
}

async function pauseIndex() {
    const r = await api('/api/pause', 'POST', {});
    if (r.success) showToast('Indexing paused.');
    refreshStatus();
}

async function resumeIndex() {
    const r = await api('/api/resume', 'POST', {});
    if (r.success) showToast('Indexing resumed.');
    refreshStatus();
}

async function purgeAll() {
    if (!confirm('PURGE ENTIRE INDEX? This cannot be undone.')) return;
    const r = await api('/api/purge/all', 'POST', {});
    if (r.success) { showToast('Index purged.'); refreshStatus(); }
    else showToast(r.error || 'Purge failed', true);
}

refreshStatus();
loadFilters();
setInterval(refreshStatus, 2500);
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
            from core.brain.RagEngine import rag_engine
            result = rag_engine.reindex_folder(path)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
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