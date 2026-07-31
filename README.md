<div align="center">

# 🧠 JARVIS — Autonomous OS Mastermind & Proactive AI Assistant

**An Elite, Voice-First, Hybrid Intelligence System with Human-in-the-Loop (HITL) Safety & Local Workspace Mastery.**

[![GitHub license](https://img.shields.io/github/license/thekaifansari01/jarvis-by-kaif-ansari?style=for-the-badge&color=2b3137)](https://github.com/thekaifansari01/jarvis-by-kaif-ansari/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18.x-339933?style=for-the-badge&logo=node.js&logoColor=white)](https://nodejs.org/)
[![Groq API](https://img.shields.io/badge/Powered%20By-Groq%20LPU-f55036?style=for-the-badge)](https://groq.com/)
[![Gemini API](https://img.shields.io/badge/Reasoning-Google%20Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-00e676?style=for-the-badge)](https://github.com/thekaifansari01/jarvis-by-kaif-ansari/pulls)

[**Key Features**](#-key-features) • [**Architecture**](#-system-architecture) • [**Installation**](#-getting-started) • [**Configuration**](#-configuration--security) • [**Tool Ecosystem**](#-integrated-tool-ecosystem) • [**Contributing**](#-contributing)

</div>

---

## 🌟 Executive Summary

**Jarvis** is a state-of-the-art, desktop-native AI Operating System designed to bridge the gap between low-latency conversational assistance and complex, multi-step autonomous task execution. Built with an emphasis on **Human-in-the-Loop (HITL) safety**, Jarvis monitors your digital environment proactively while never executing irreversible system actions without explicit user consent.

Unlike conventional chatbots, Jarvis operates directly on your local system — combining **real-time speech recognition**, **vector-based long-term memory**, **retrieval-augmented generation (RAG)**, and **native OS control** into a unified, highly extensible personal assistant.

---

## ✨ Why Jarvis Stands Out

| Icon | Feature | Description |
|:---:|:---|:---|
| 🛡️ | **Proactive Watchdog** | Background Pub/Sub & event listeners for Gmail, WhatsApp, and Calendar with intelligent spam filtering. |
| 🧠 | **Hybrid Intelligence** | Semantic routing switches between low-latency FastBrain and deep-reasoning AgenticBrain automatically. |
| 🗣️ | **Human-in-the-Loop** | Never modifies critical calendars, files, or emails without voice/text confirmation from the user. |
| 📚 | **Lifelong Episodic LTM** | Vector-backed persistent memory (ChromaDB) that learns user facts, preferences, and emotional context. |

---

## 🏗️ System Architecture

Jarvis utilizes a modular, event-driven architecture that separates fast conversational inference from stateful, multi-tool agentic planning:

```mermaid
graph TD
    %% Input Layer
    user_input[👤 User Input] --> input_router{Input Type}
    input_router -->|Voice| wake_word[🎙️ Picovoice Wake Word]
    input_router -->|Text / Hotkey| popup_ui[⌨️ Hotkey Popup UI]
    wake_word --> stt_engine[⚡ Deepgram Nova-2 STT]

    %% Router Layer
    stt_engine --> semantic_router[🚦 Hybrid Semantic Router]
    popup_ui --> semantic_router

    %% Intelligence Engine
    semantic_router -->|Direct / Fast Command| fast_brain[⚡ FastBrain<br/>Groq Llama-3.3-70B]
    semantic_router -->|Multi-step / File / Comms| agent_brain[🧠 AgenticBrain<br/>Gemini Gemma-4-31B]

    %% Memory & Context Layer
    subgraph Memory Ecosystem
        ltm_db[(🗄️ ChromaDB LTM<br/>Episodic Memory)]
        rag_db[(📚 ChromaDB RAG<br/>Workspace Documents)]
        context_jsonl[📜 JSONL Rolling History<br/>15-Day Context]
        profile_json[👤 User Profile & Mood]
    end

    agent_brain <--> Memory
    fast_brain <--> Memory

    %% Execution & Tools Layer
    subgraph Native Tool Ecosystem
        comms_tools[📨 Gmail / WhatsApp / Calendar]
        fs_tools[📂 File CRUD & Workspace RAG]
        sys_tools[💻 OS Control / Apps / Terminal]
        search_tools[🌐 Tavily Web / ArXiv / Scraper]
    end

    agent_brain --> comms_tools
    agent_brain --> fs_tools
    agent_brain --> sys_tools
    agent_brain --> search_tools

    %% Proactive Background Layer
    subgraph Proactive HITL Watchdog
        listeners[📡 Gmail / WhatsApp / Reminders]
        queue[📦 Thread-safe Event Queue]
        scout[🛡️ Proactive Scout Agent]
    end

    listeners --> queue --> scout
    scout -->|Informational FYI| tts_out[🔊 Edge TTS / Orpheus Audio]
    scout -->|Action Suggested| agent_brain
```

---

## 🧠 Core Intelligence Modules

### 1. 🚦 Hybrid Semantic Router

* **Zero-Latency Routing:** Dynamically inspects user prompts to classify them as either **FAST** (stateless, casual chat, quick OS toggles) or **AGENTIC** (deep reasoning, file editing, API automation).
* **Fallback Rule-Engine:** Built-in heuristics ensure guaranteed routing even during cloud API degradation.

### 2. ⚡ FastBrain (Groq LPU)

* Optimized for sub-second conversational responses using `llama-3.3-70b-versatile`.
* Handles direct desktop controls, playback queries, and factual Q&A without tool overhead.

### 3. 🧠 AgenticBrain (Gemini Reasoning)

* Uses `gemma-4-31b-it` with native function-calling for complex multi-step execution.
* Employs a strict **4-Pillar Reasoning Contract** (Fact Audit -> Missing Piece Check -> Safety Audit -> Pragmatic Exit) to prevent infinite loops and hallucinations.

### 4. 🛡️ Proactive Scout & HITL Security

* **Silent Background Execution:** Evaluates batched background notifications without hijacking active desktop UI or full-screen applications.
* **Consent Gate:** Asks concise confirmation questions before executing permanent changes (e.g., *"Meeting reschedule request received. Should I update your Google Calendar?"*).

---

## 🛠️ Integrated Tool Ecosystem

| Category | Supported Capabilities | Tech / API Bridge |
| --- | --- | --- |
| 📨 **Communication** | Send/read Gmails, dispatch WhatsApp messages, manage Google Calendar events. | Gmail Pub/Sub, Baileys Node.js Server, Calendar OAuth |
| 📂 **Workspace & File OS** | Single-file CRUD, directory scanning, code generation, local markdown RAG indexing. | Python `os`/`pathlib`, ChromaDB Vector Index |
| 🌐 **Search & Deep Research** | Live web scraping, academic research (ArXiv), YouTube transcripts, synthesis reports. | Tavily Search, BeautifulSoup, ArXiv API |
| 💻 **System Automation** | Launch/close desktop apps, hardware volume/brightness, screenshots, clipboard CRUD. | Python OS Bindings, Win32 API, Pygame |
| 🎨 **Creative AI** | High-speed local/cloud image generation and editing. | Flux.1-Schnell, AI Horde |

---

## 🚀 Getting Started

### 1. System Prerequisites

* **OS:** Windows 10/11 (Recommended for full native Win32/Registry protocol features)
* **Python:** `>= 3.10`
* **Node.js:** `>= 18.0` (Required for WhatsApp Baileys background service)
* **Git:** Latest stable release

### 2. Quick Install

```bash
# Clone the repository
git clone https://github.com/thekaifansari01/jarvis-by-kaif-ansari.git
cd jarvis-by-kaif-ansari

# Create and activate a Python Virtual Environment
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux / macOS

# Install required Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies for WhatsApp Service
cd tools/Messanger/whatsapp/BaileysServer
npm install
cd ../../..
```

### 3. Register Desktop URI Protocol

To enable seamless OAuth web-authentication for Gmail and Google Calendar (`jarvis://` callback), run:

```bash
python SetupRegistry.py
```

---

## ⚙️ Configuration & Security

Create a `.env` file in your root project directory by copying the provided example template:

```bash
cp .env.example .env
```

### Full Environment Variables Example (`.env.example`)

Copy and paste the following into your `.env` file, then fill in your API keys:

```env
# ============================================
# API KEYS - Add your keys below
# ============================================
USER_NAME=
GROQ_API_KEY=
TOGETHER_AI=
TAVILY_API_KEY=
GEMINI_API_KEY=
DEEPGRAM_API_KEY=
REGOLO_API_KEY=

# ============================================
# API ENDPOINTS & MODELS
# ============================================
API_BASE_URL=https://jarvis-oauth-server.vercel.app
REGOLO_BASE_URL=https://api.regolo.ai/v1
REGOLO_MODEL=gemma4-31b

# ============================================
# AGENT CONFIGURATION
# ============================================
AGENT_PRIMARY_PROVIDER=regolo
AGENT_FALLBACK_PROVIDER=gemini
REGOLO_THINKING_ENABLED=True

# ============================================
# ⚠️ DO NOT CHANGE THE FOLLOWING
# ============================================
# API_BASE_URL         - OAuth server endpoint
# REGOLO_BASE_URL      - Regolo API endpoint
# REGOLO_MODEL         - Default model for Regolo
```

> **Security Note:** Never commit your `.env` or `Data/SessionCookies/` directory to public version control. They are excluded via `.gitignore` by default.

---

## 🎮 Execution Modes

Jarvis can be launched in multiple operational configurations depending on your workflow:

```bash
# 1. Full Autonomous Voice & Desktop Mode (Default)
python main.py

# 2. Terminal Text-Only Testing Mode (No Microphone Required)
python main.py test_jarvis

# 3. Silent Mode (Wake Word Disabled, Trigger via Hotkeys Only)
python main.py no_wake
```

### Keyboard Shortcuts

* `Ctrl + Shift + J`: Open Floating Text Input & Markdown UI Popup.

---

## 📁 Repository Anatomy

```
jarvis-by-kaif-ansari/
├── core/
│   ├── brain/              # Neural engines (FastBrain, AgenticBrain, Smart Router)
│   ├── voice/              # Deepgram STT, Picovoice Wake Word, Edge TTS engines
│   ├── ui/                 # ZMQ-powered floating PyQt5 UI widgets & status panels
│   └── logger/             # Thread-safe colored terminal loggers (Rich)
├── tools/
│   ├── Messanger/          # Gmail Pub/Sub & Baileys WhatsApp bridges
│   ├── SystemTools/        # Win32 OS controls, hardware toggles, and clipboard
│   ├── SearchTools/        # Tavily deep research, ArXiv, and web scrapers
│   └── workspace/          # Local filesystem RAG and file CRUD executor
├── Proactive/
│   ├── proactive_agent.py  # Background Scout logic & HITL consent manager
│   └── event_queue.py      # Thread-safe time-window event batching queue
├── Data/                   # Local state (ChromaDB vectors, user profile, cookies)
├── main.py                 # Primary entry point & service supervisor
└── requirements.txt        # Verified Python production dependencies
```

---

## 🛣️ Roadmap & Future Scope

* [x] **Phase 1:** Real-time Voice Wake Word & Hybrid Semantic Routing.
* [x] **Phase 2:** ChromaDB Episodic Memory & Local Workspace RAG Engine.
* [x] **Phase 3:** Proactive HITL Watchdog for Gmail, WhatsApp, and Calendar.
* [ ] **Phase 4:** Dockerized Sandbox Execution for running untrusted code safely.
* [ ] **Phase 5:** Full Multi-platform macOS & Linux native system accessibility.

---

## 🤝 Contributing

We welcome contributions from developers, researchers, and AI enthusiasts!

1. **Fork** the repository.
2. **Create** a feature branch (`git checkout -b feature/AdvancedTooling`).
3. **Commit** your changes with clear, descriptive messages.
4. **Push** to your fork (`git push origin feature/AdvancedTooling`).
5. **Open** a Pull Request for review.

---

## 📄 License & Attribution

This project is open-source and licensed under the **MIT License** — see the [LICENSE](LICENSE) file for complete details.

**Built with ❤️ and pragmatic engineering by Kaif Ansari**

*If this project inspired your own AI architecture, consider leaving a ⭐ on the repository!*