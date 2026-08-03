<div align="center">

# 🧠 J.A.R.V.I.S. — The Autonomous AI Agent

> **A Windows-first, voice-enabled, hybrid-intelligence AI Operating System with multi-LLM failover, zero line-drift code editing, lifelong memory, proactive HITL safety, and a native reactive UI.**

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-18.x-339933?style=for-the-badge&logo=node.js&logoColor=white)](https://nodejs.org/)
[![Groq LPU](https://img.shields.io/badge/Powered%20By-Groq%20LPU-f55036?style=for-the-badge)](https://groq.com/)
[![Gemini](https://img.shields.io/badge/Reasoning-Google%20Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![Regolo AI](https://img.shields.io/badge/Agentic-Regolo%20MoE-FF6F00?style=for-the-badge)](https://regolo.ai)
[![OpenRouter](https://img.shields.io/badge/Failover-OpenRouter-FF6B6B?style=for-the-badge)](https://openrouter.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-00e676?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-00e676?style=for-the-badge)](https://github.com/thekaifansari01/jarvis-by-kaif-ansari/pulls)

**Built by a 17-year-old solo developer. Commerce background. BCA first year. No team. No funding. Just late nights, coffee, and a burning passion to build the impossible.** ☕

</div>

---

## 📖 Table of Contents

<div align="center">

**Core**  
[🌟 What Makes JARVIS Special](#-what-makes-jarvis-special) • [🏗️ System Architecture](#️-system-architecture) • [⚡ FastBrain vs 🧠 AgenticBrain](#-fastbrain-vs--agenticbrain) • [💻 Autonomous Software Engineering](#-autonomous-software-engineering--zero-line-drift) • [🎨 UI & Visualization Ecosystem](#-ui--visualization-ecosystem) • [🛡️ Resilience & Security Architecture](#️-resilience--security-architecture) • [🧠 Memory & Long-Term Recall](#-memory--long-term-recall-ltm-ecosystem)

**Tools & Usage**  
[🛠️ Integrated Tool Ecosystem](#️-integrated-tool-ecosystem--native-executors) • [📋 Example Requests](#-example-requests--see-jarvis-in-action) • [🚀 Advanced Scenarios](#-advanced-scenarios) • [🚀 Getting Started](#-getting-started) • [⚙️ Configuration](#️-configuration--enterprise-security) • [📂 Repository Anatomy](#-repository-anatomy) • [🔧 Troubleshooting](#-troubleshooting) • [🤝 Contributing](#-contributing) • [📄 License](#-license)

</div>

---

## 🌟 What Makes JARVIS Special

JARVIS isn't just another ChatGPT wrapper. It's a **desktop-native AI Operating System** and **Autonomous Agent** that bridges the gap between low-latency conversational AI and complex, multi-step engineering execution.

| Icon | Feature | Why It Matters |
|:---:|:---|:---|
| 💻 | **Zero Line-Drift Code Editing** | Uses exact `replace_block` diffs instead of fragile line numbers — eliminates the classic "line-drift bug" that plagues Claude Code and other AI agents. |
| 🛡️ | **Proactive HITL Safety** | Background listeners for Gmail/WhatsApp/Calendar. The agent *never* modifies critical files or schedules without explicit user consent. |
| 🔄 | **Multi-LLM Auto-Failover** | Seamlessly switches between **Regolo**, **Gemini**, and **OpenRouter** (Claude 3.7, o1, DeepSeek-V3) if the primary provider hits rate limits. |
| 🧠 | **Hybrid Semantic Routing** | Cloud Regolo router + local rule-based fallback — automatically routes commands to ultra-fast **FastBrain** or deep-reasoning **AgenticBrain**. |
| 📚 | **Lifelong Episodic LTM** | ChromaDB-backed persistent memory with daily Groq summarization. Remembers conversations from *months* ago. |
| ⚙️ | **Enterprise Resilience** | Dedicated **ServiceWatchdog** monitors background processes (STT Popup, Baileys) and auto-restarts them if they crash. |
| 🎨 | **Reactive UI Ecosystem** | ZMQ-powered floating Agent Panel, live markdown typing popup with async image previews, and native STT/Input popups. |
| 🗣️ | **Voice-First Multimodal** | Deepgram STT + Edge TTS + Vision (OCR/object detection) + Image Generation (Flux/AI Horde). |

---

## 🏗️ System Architecture

JARVIS uses a modular, event-driven architecture that separates fast conversational inference from stateful, multi-tool agentic engineering:

```mermaid
flowchart TD
    User[👤 Voice or Text Command] --> Input{Input Type}
    Input -->|Voice| Wake[🎙️ openWakeWord]
    Input -->|Text| Hotkey[⌨️ Ctrl+Shift+J Popup]
    Wake --> STT[⚡ Deepgram Nova-2 STT]
    Hotkey --> Router[🚦 Hybrid Semantic Router]
    STT --> Router
    Router -->|Fallback| LocalRouter[🔄 Local Rule-Based Router]
    
    Router -->|Simple / Stateless| FastBrain[⚡ FastBrain<br/>Groq Llama-3.3-70B]
    Router -->|Complex / Stateful| AgenticBrain[🧠 AgenticBrain<br/>Regolo/Gemini/OpenRouter]
    
    AgenticBrain --> Providers[🔌 Provider Abstraction Layer]
    Providers --> Regolo[Regolo MoE]
    Providers --> Gemini[Gemini Reasoning]
    Providers --> OpenRouter[OpenRouter<br/>Claude 3.7 / o1 / DeepSeek]
    
    subgraph Memory[🧠 Memory Ecosystem]
        LTM[(🗄️ ChromaDB LTM<br/>Episodic Archive)]
        RAG[(📚 ChromaDB RAG<br/>Workspace Docs)]
        JSONL[📜 JSONL Rolling History<br/>15-Day Context]
        Profile[👤 User Profile & Mood]
    end
    
    AgenticBrain <--> Memory
    FastBrain <--> Memory
    
    subgraph Tools[🛠️ Native Tool Ecosystem]
        Code[💻 Repo-Map / Replace-Block / AST Linter]
        Comms[📨 Gmail / WhatsApp / Calendar]
        System[⚙️ OS Control / Apps / Clipboard]
        Search[🌐 Tavily / ArXiv / Scraper]
        Vision[👁️ Vision Multimodal / OCR]
        Image[🎨 Image Gen / Edit]
    end
    
    AgenticBrain --> Tools
    FastBrain --> System
    FastBrain --> Search
    
    subgraph UI[🎨 UI & Visualization]
        AgentPanel[🖥️ ZMQ Agent Panel]
        TypingPopup[📝 Markdown Typing Popup]
        STTPopup[🗣️ STT Status Popup]
        InputPopup[⌨️ Input Popup]
    end
    
    AgenticBrain -->|ZMQ PUB| AgentPanel
    FastBrain -->|typing_status.json| TypingPopup
    STT --> STTPopup
    InputPopup --> Router
    
    subgraph Proactive[🛡️ Proactive HITL Watchdog]
        Listeners[📡 Gmail / WhatsApp / Reminders]
        Scout[🛡️ Proactive Scout Agent]
        Consent[🔒 HITL Consent Gate]
    end
    
    Listeners --> Scout -->|Suggested Action| AgenticBrain
    AgenticBrain -->|Requires Permission| Consent -->|User Confirms| AgenticBrain
    
    subgraph Resilience[⚙️ Resilience Layer]
        Watchdog[🛡️ ServiceWatchdog]
        Failover[🔄 Provider Failover]
        Recovery[🔄 Two-Strike Rule]
    end
    
    Watchdog -.->|Monitors| System
    Failover -.-> Providers
    Recovery -.-> AgenticBrain
```

---

## ⚡ FastBrain vs 🧠 AgenticBrain

JARVIS uses a **Hybrid Semantic Router** (Regolo API + Local Keyword Fallback) to split commands. Here's exactly what each brain handles:

| Feature / Capability | ⚡ FastBrain (Groq LPU) | 🧠 AgenticBrain (Regolo/Gemini/OpenRouter) |
| :--- | :--- | :--- |
| **Core Philosophy** | Stateless, Sub-second latency, Direct OS toggles. | Stateful, Deep reasoning, Tool-calling Master. |
| **Routing Trigger** | Short commands, casual chat, simple toggles. | 25+ words, file ops, code gen, communication. |
| **System Controls** | Open/Close Apps, URLs, YouTube direct play. | Full system automation via Python scripts & Terminal. |
| **Hardware Toggles** | Volume (Set/Inc/Dec), Brightness, Mute, Screenshot, Lock/Sleep. | *(Same as FastBrain, but part of complex workflows)* |
| **File Operations** | ❌ Cannot modify files. | ✅ Full CRUD, `repo_map`, `replace_block` (Zero Drift), `create_many`. |
| **Communication** | ❌ No email/WhatsApp. | ✅ Send Gmails, WhatsApp messages, Fetch chat history. |
| **Code Execution** | ❌ No Python/Terminal execution. | ✅ `run_python_code` (preferred), `execute_terminal_command`. |
| **Memory Recall** | ❌ No personal LTM memory. | ✅ `memory_actions` (15-day logs + Lifetime episodic recall). |
| **Multimodal** | ❌ No vision. | ✅ `vision` (Image/Video analysis, OCR, object detection). |
| **Research** | ❌ Simple web search only (`quick_web_search`). | ✅ `deep_research` (420s multi-source synthesis), ArXiv, YouTube transcripts. |
| **Proactive HITL** | ❌ No. | ✅ Strict Partner Confirmation Mode. Asks consent before permanent changes. |

---

## 💻 Autonomous Software Engineering & Zero Line-Drift

JARVIS features a built-in software engineering engine enabling autonomous project scaffolding, bug hunting, and safe code refactoring:

### 1. 📂 Codebase Architecture Mapping (`repo_map`)
Before writing a single line, JARVIS inspects project structures natively. It automatically filters out heavy dependency directories (`node_modules`, `.venv`, `__pycache__`, `.git`, `Data`) to feed a clean, token-efficient ASCII tree directly into the LLM context window.

### 2. 🎯 Zero Line-Drift Block Editing (`replace_block`)
Eliminates the classic "Line Drift Bug" by replacing exact multi-line code diff blocks instead of fragile line numbers.
- **Windows Safe:** Normalizes Windows (`\r\n`) and POSIX (`\n`) line endings automatically for safe cross-platform matching.
- **Cost Efficient:** Reduces token usage by sending only the diff, not the whole file.

### 3. 🛡️ Instant AST Linter & Self-Correcting Loop
Embeds an automated post-write linter hook (`py_compile`) that validates syntax instantly upon file creation or modification.
- If a `SyntaxError` or indentation error occurs, JARVIS catches the compiler traceback and **autonomously self-corrects** the code in the very next step (`Two-Strike Rule`) without requiring human intervention.

### 4. ⚡ Multi-File Batching & Anti-Truncation
Dynamically routes small boilerplate tasks to native `create_many` CRUD tools while leveraging batched Python scripting (`run_python_code`) to build entire modular web applications in a single execution step (~15 seconds).

### 5. 🔧 Terminal & Python REPL Execution
- `execute_terminal_command`: For OS system processes, package installs (`pip`/`npm`), git operations, or external executables.
- `run_python_code`: Preferred for OS discovery, data tasks, recursive folder searching, file filtering, complex data parsing, and multi-step logic.

---

## 🎨 UI & Visualization Ecosystem

JARVIS features a full-fledged, reactive UI suite built with **PyQt5** and **ZMQ** for real-time status updates, markdown rendering, and voice/text interactions.

### 1. 🖥️ Agent Panel (`core/ui/agent_panel.py`)
- **Role:** Floating, glass‑morphism status panel that shows the agent's **thought process**, **current action**, and **observation** in real time.
- **Communication:** Subscribes to ZMQ PUB socket (`tcp://127.0.0.1:5555`) – `agent_status.py` publishes `AGENT_UPDATE` messages.
- **Dynamic Glow:** Border glow changes color based on action type (Search = Cyan, Deep Task = Pink, File Ops = Orange, Communication = Green, Vision = Teal, etc.).
- **Auto‑Resize & Animation:** Smoothly adapts width/height to content and slides in/out with easing curves.
- **Smart Truncation:** Limits thought to 800 characters and observation to 200 characters to keep UI clean.
- **Font Fallback:** Automatically switches between English and Devanagari fonts based on text content.

### 2. 📝 Typing Popup (`core/ui/Popup/`)
- **Role:** Floating typewriter‑style popup that streams JARVIS's responses in real time with full markdown rendering.
- **Communication:** Reads `Data/typing_status.json` (written by `typing_status.py`) every 50ms.
- **Async Markdown Rendering:**
  - **Code Blocks:** Syntax‑highlighted using Pygments (Monokai theme) with a macOS‑style header.
  - **Tables, Lists, Blockquotes:** Fully supported with elegant styling.
  - **Images:** Supports local (`file://`) and remote images with async downloading and LRU caching (max 50 entries).
  - **Link Previews:** Automatically fetches rich previews via microlink.io API (`preview://` scheme).
  - **YouTube Previews:** Embeds `maxresdefault.jpg` thumbnails with a custom play button overlay.
- **Auto‑Scroll:** Sticks to the bottom while typing; allows manual scrolling once completed.
- **Smart Auto‑Close:** Closes automatically after a few seconds for short messages (<40 words) to reduce clutter.

### 3. 🗣️ STT Popup (`Bin/SttPopup.exe`)
- **Role:** Small floating indicator that appears when voice input is active (speech‑to‑text listening).
- **Behavior:** `BackgroundServices.start_stt_popup()` spawns it. `stt_status.py` controls visibility (show/hide) based on STT engine state.

### 4. ⌨️ Input Popup (`Bin/InputPopup.exe`)
- **Role:** Triggered by global hotkey `Ctrl+Shift+J` – opens a lightweight text input window for typing commands.
- **Integration:** `HotKeyManager.py` spawns the process, reads stdout for `JARVIS_CMD:::` prefix, and submits the command to `main_command_processor`.

### 5. ⚙️ Core Rendering Engines (`AsyncBrowser.py` & `TextParser.py`)
- **AsyncBrowser:** A custom `QTextBrowser` subclass that handles async image downloads, manages a fail‑safe cache, and generates placeholders for loading/error states.
- **TextParser:** A background `QThread` that parses markdown, syntax‑highlights code, injects link preview tokens, and generates styled HTML – keeping the UI thread snappy.

---

## 🛡️ Resilience & Security Architecture

### 1. 🔄 Multi-LLM Auto-Failover (Provider Abstraction)
JARVIS doesn't rely on a single AI provider. The `BaseLLMProvider` abstract class implements **Regolo**, **Gemini**, and **OpenRouter** providers.
- **Primary:** Configurable via `AGENT_PRIMARY_PROVIDER`.
- **Fallback:** If quota is exhausted (429 error), it auto-switches to `AGENT_FALLBACK_PROVIDER` without crashing the agent loop.
- **Provider Support:** Regolo, Gemini, OpenRouter (Claude 3.7, o1, DeepSeek-V3, and 200+ models).

### 2. 🛡️ ServiceWatchdog (Background Process Guardian)
A dedicated daemon thread runs in the background, checking the health of critical subprocesses every 5 seconds:
- **Baileys Server** (WhatsApp Bridge)
- **STT Popup** (Voice Status UI)
- If a process is down, it attempts a restart up to `max_retries=3` with a 15-second cooldown period, ensuring maximum uptime.

### 3. 🔒 Human-in-the-Loop (HITL) Consent Protocol
- **Proactive Trigger Detection:** If the `Proactive Scout` detects an email/WhatsApp asking to reschedule a meeting, the AgenticBrain enters *Partner Confirmation Mode*.
- **Zero Unauthorized Execution:** The agent never executes `calendar_action`, `email_action`, or `file_operations` for critical modifications without the user explicitly saying *"Haa kar de"*, *"Yes do it"*, or *"Theek hai kardo"*.
- **TTL Expiry:** Pending confirmations auto-expire after 60 seconds to prevent stale memory injections.

### 4. 🔄 Two-Strike Error Recovery
If a tool or script fails:
- **Strike 1:** Reads stderr/stdout, fixes syntax/logic, and retries once with an improved script.
- **Strike 2:** If it fails a second time, ABANDONS that approach immediately and pivots to an alternative strategy.
- **Pragmatic Completion:** Avoids endless iterations for minor cosmetic perfection. Once the essential data/file is generated correctly, it invokes `complete_task`.

---

## 🧠 Memory & Long-Term Recall (LTM) Ecosystem

JARVIS employs a sophisticated three-tier memory system to maintain context across sessions:

### 1. 📜 Rolling JSONL History (Short-Term)
- Stores the last 15 days of conversation in `master_chat_history.jsonl`.
- Append-only architecture ensures zero data corruption during rapid write operations.
- Automatically prunes messages older than 15 days and archives them to LTM.

### 2. 🗄️ Lifetime Episodic Memory (Long-Term)
- Every 24 hours, the `LifetimeMemory` engine archives old chats.
- Uses Groq (`GROQ_SUMMARY_MODEL`) to extract dense, third-person factual summaries (ignoring small talk).
- Embeds summaries using `gemini-embedding-2` (768 dims) and stores them in a **ChromaDB** collection (`jarvis_episodic_memory`).

### 3. 📚 Workspace RAG (Vector Database)
- Indexes files in `Documents/Jarvis/RAG/` (supports `.txt`, `.md`, `.json`, `.py`, `.js`, `.csv`).
- **Smart Chunking:** Code files are split by `def`/`class`; text files by paragraphs.
- **Hash-Based Re-indexing:** Only re-indexes files that have changed (MD5 hash check), saving API costs.
- **Local Keyword Search:** Uses ChromaDB's `$contains` operator for fast, API-free local searches.

### 4. 👤 User Profile & Mood Tracking
- `user_bio.json`: Hard, unchanging facts about the user.
- `preferences.json`: Actionable preferences (likes, dislikes).
- `user_mood.json`: Mood history with timestamps.
- AI automatically extracts insights from conversations using Groq summarization.

---

## 🛠️ Integrated Tool Ecosystem & Native Executors

| Category | Supported Capabilities | Tech / API Bridge |
| :--- | :--- | :--- |
| 💻 **Software Engineering** | Project `repo_map`, Exact `replace_block` diffs, Post-edit syntax linting, Multi-file batch creation (`create_many`). | Python AST / `py_compile` / `fileEditor.py` |
| 📨 **Communication** | Send/read Gmails, Dispatch WhatsApp messages/files, Fetch WhatsApp chat history, Manage Google Calendar events. | Gmail Pub/Sub, Baileys Node.js Server, Calendar OAuth |
| 📂 **Workspace & RAG** | Single-file CRUD, Recursive directory scanning, Local markdown RAG indexing with hash-based change detection. | Python `os`/`pathlib`, ChromaDB Vector Index |
| 🌐 **Search & Research** | Live web scraping, Academic research (ArXiv), YouTube transcript summarization, Multi-source synthesis reports. | Tavily Search, BeautifulSoup, ArXiv API |
| ⚙️ **System Automation** | Launch/close desktop apps, Hardware volume/brightness, Screenshots, Clipboard CRUD (Read/Write). | Python OS Bindings, Win32 API, Pygame |
| 👁️ **Multimodal Vision** | Image/Video analysis, Object detection, OCR extraction from scanned documents/photos. | Gemini/Regolo Vision models |
| 🎨 **Image Generation** | Text-to-image generation, Image-to-image editing. | Regolo Qwen-Image / Together FLUX / AI Horde |

---

## 📋 Example Requests — See Jarvis in Action

### ⚡ FastBrain — Blazing Fast (< 1.5 sec response)

| Feature | Example Command | What Jarvis Does |
| :--- | :--- | :--- |
| **System Automation** | `"Open Chrome, play 'Blinding Lights' on Spotify, and set volume to 70%"` | Opens Chrome, launches Spotify via URI, plays the song, and adjusts system volume — **all in one command.** |
| **Hardware Toggles** | `"Set brightness to 50% and take a screenshot"` | Changes display brightness to 50% and captures a full-screen screenshot in under 2 seconds. |
| **Smart Web Search** | `"Get today's weather in Mumbai and the latest IPL 2025 final score"` | Performs two parallel web searches and returns a concise, combined summary — **no agentic overhead.** |
| **YouTube Direct** | `"Play 'Arijit Singh latest song' on YouTube"` | Opens YouTube in browser and directly plays the song via `pywhatkit`. |
| **System Control** | `"Lock the system and set an alarm for 5 minutes later"` | Locks PC immediately and schedules a system alarm/reminder. |
| **Media Playback** | `"Play 'Atif Aslam hits' playlist on Spotify"` | Opens Spotify desktop app and starts the playlist via URI protocols. |
| **Quick Info** | `"What is today's date and time?"` | Returns current system date/time with timezone info. |
| **Clipboard** | `"Read the clipboard and write 'Hello World' to it"` | Reads clipboard, then writes text to it — **instant clipboard management.** |
| **Power Actions** | `"Put the PC to sleep"` | Puts system to sleep instantly. |
| **App Management** | `"Open Notepad and Calculator, then close VSCode"` | Launches multiple apps while closing another — **batch app control.** |

---

### 🧠 AgenticBrain — Deep Reasoning, Autonomous Engineering

| Feature | Example Command | What Jarvis Does |
| :--- | :--- | :--- |
| **Multi-Step Software Engineering** | `"Give me a repo map of my project, install missing dependencies from requirements.txt, and fix the bug in main.py that has been crashing since yesterday"` | 1. Inspects project structure via `repo_map`.<br>2. Reads `requirements.txt` and runs `pip install` for missing packages.<br>3. Analyzes `main.py`, finds the bug, and uses `replace_block` to fix it — **all autonomously.** |
| **Zero Line-Drift Code Edit** | `"Convert the 'get_user_data' function in app.py to async and add error handling"` | Reads the exact block, replaces it with async version + try-except — **without touching any other line.** |
| **Self-Correcting Python** | `"Write a Python function to generate the Fibonacci sequence. If there's a syntax error, fix it."` | Writes the function, catches `py_compile` errors, and **self-corrects** in the next step. |
| **Deep Research & Synthesis** | `"Research and compare NVIDIA's latest AI chips with AMD's MI400 series, and generate a benchmark report"` | Searches web, reads multiple sources, synthesizes data, and returns a **structured markdown report** with tables and citations. |
| **Academic Research** | `"Search ArXiv for 'transformer attention optimization' papers and summarize the top 2025 papers"` | Searches ArXiv, fetches abstracts, and summarizes key findings — **researcher-level automation.** |
| **Multimodal Vision** | `"What is in this screenshot? Extract the text from this image."` | Inspects images/videos via Gemini vision, identifies objects, and extracts embedded text (OCR). |
| **YouTube Deep Dive** | `"Summarize this YouTube link and extract 5 key takeaways"` | Fetches transcript, summarizes content, and extracts 5 bullet-point insights. |
| **Email + Calendar** | `"Send an email to Kaif that the meeting has been moved to 5 PM, and update the calendar accordingly"` | Sends email and updates Google Calendar — **with HITL consent gate.** |
| **WhatsApp Automation** | `"Send a WhatsApp message to Rahul that I'll be 10 minutes late, and fetch yesterday's chat history"` | Sends message and fetches chat history via Baileys — **all in one command.** |
| **Memory Recall** | `"What project did I discuss about AI agents three months ago?"` | Searches ChromaDB LTM, fetches episodic memory, and returns the conversation context. |
| **Codebase Understanding** | `"Explain the architecture of this codebase and generate a dependency graph"` | Scans project, generates `repo_map`, analyzes imports, and creates a visual dependency graph. |
| **Web Scraping & Analysis** | `"Scrape the content of this webpage and perform sentiment analysis"` | Reads the page, extracts key text, and performs sentiment/tonality analysis. |
| **Image Generation** | `"Generate a cyberpunk JARVIS wallpaper with neon purple glow"` | Generates image via Flux/AI Horde and saves it to desktop. |
| **System + File Operations** | `"Create a 'Projects' folder on the desktop, create 5 Python files inside it, and define a class in each file"` | Uses `run_python_code` to batch-create multiple files with boilerplate classes — **all in 15 seconds.** |
| **Proactive HITL** | *(Jarvis detects email about meeting reschedule)* → `"Bhai, Ram ka mail aaya hai ki meeting 5 baje shift ho gayi. Kya main calendar update kar doon?"` | Enters **Partner Confirmation Mode**, asks for consent, and executes only after user says *"Haan kar de"*. |

---

### 🆚 FastBrain vs AgenticBrain — Quick Summary

| Command Type | Route | Typical Time |
| :--- | :--- | :--- |
| System controls, hardware toggles, simple searches | ⚡ **FastBrain** | `< 1.5 sec` |
| File editing, code generation, communication, research | 🧠 **AgenticBrain** | `15-60 sec` |
| Multi-step tasks with tool calls | 🧠 **AgenticBrain** | `30-120 sec` |
| Commands with 25+ words or complex intent | 🧠 **AgenticBrain** | Automatic |

---

## 🚀 Advanced Scenarios

| Scenario | Example Command | Jarvis's Autonomous Action Plan |
| :--- | :--- | :--- |
| **Autonomous Bug Fixing** | `"F:/legacy-invoice-app mein project hai. pytest -v run karo, failures dekho, fir 3 bugs fix karo — utils.py mein calculate_total() mein tax_rate ko float() mein convert karo, normalize_name() mein None handle karo, models.py mein Invoice.summary() mein self.total ko call karo (self.total()) — har fix ke baad pytest -v run karke verify karo, saare 10 tests pass hone par complete_task call karo."` | 1. `repo_map` se project structure inspect karega.<br>2. `pytest -v` run karega, 6 failures identify karega.<br>3. `replace_block` se pehla bug fix karega (`tax_rate` → `float(tax_rate)`).<br>4. `pytest -v` run karega → 4 failures.<br>5. `replace_block` se doosra bug fix karega (`None` handle in `normalize_name`).<br>6. `pytest -v` run karega → 2 failures.<br>7. `replace_block` se teesra bug fix karega (`self.total` → `self.total()`).<br>8. `pytest -v` run karega → **10/10 PASS**.<br>9. `complete_task` call karega with detailed report. |
| **Full-Stack App with Testing** | `"Desktop par 'TaskFlow' naam ka project banao. FastAPI backend with SQLite, React frontend with Tailwind, aur 10+ unit tests. Phir pytest run karo aur saare tests pass karo."` | 1. Folder structure create karega (`backend/`, `frontend/`, `tests/`).<br>2. `requirements.txt` aur `package.json` generate karega.<br>3. FastAPI app with CRUD endpoints likhega.<br>4. React frontend with Tailwind components likhega.<br>5. `pytest` tests likhega for all endpoints.<br>6. `npm install` aur `pip install` run karega.<br>7. `pytest` run karega — agar fail ho, toh `replace_block` se fix karega.<br>8. Saare tests pass hone par `complete_task` call karega. |
| **Production Debugging with Profiling** | `"main.py mein memory leak hai. memory_profiler install karo, profile run karo, bottleneck identify karo, fix karo, aur verify karo ki leak fix ho gayi."` | 1. `pip install memory_profiler` run karega.<br>2. `mprof run main.py` run karega.<br>3. `mprof plot` se graph generate karega.<br>4. Leak identify karega (e.g., unclosed file handles, large lists).<br>5. `replace_block` se fix apply karega.<br>6. Dubara `mprof run main.py` run karega — verify memory stable hai.<br>7. `complete_task` call karega with before/after comparison. |
| **Data Analysis Pipeline** | `"Iss CSV file ko analyze karo. Missing values handle karo, outliers hatao, correlation matrix generate karo, aur plotly visualization banao. Phir ek summary report generate karo."` | 1. `pandas` se CSV read karega.<br>2. Missing values detect aur handle karega (mean/median imputation).<br>3. Outliers detect karega (IQR method) aur remove karega.<br>4. Correlation matrix generate karega.<br>5. `plotly` se interactive heatmap + scatter plots generate karega.<br>6. Summary report generate karega (mean, median, std, skewness).<br>7. Sab files `output/` folder mein save karega.<br>8. `complete_task` call karega with report. |
| **Proactive HITL — Email + Calendar Automation** | *(Jarvis detects email: "Meeting rescheduled to 5 PM")* → `"Bhai, Ram ka mail aaya hai ki meeting 5 baje shift ho gayi. Kya main calendar update kar doon?"` → *User: "Haan kar de"* → `"Meeting updated to 5 PM. Sending confirmation email to Ram."` | 1. Proactive listener email detect karega.<br>2. Scout agent email classify karega (important, action required).<br>3. **Partner Confirmation Mode** enter karega — user se puchega.<br>4. User "Haan kar de" bolega → `calendar_action` call karega.<br>5. Calendar event update karega (time change).<br>6. `email_action` se Ram ko confirmation bhejega.<br>7. `complete_task` call karega with success report. |
| **System Setup Automation** | `"Mere naye laptop par Python, Node.js, Docker, VS Code extensions, aur project dependencies install karo. Phir .env file generate karo with template."` | 1. `winget` / `choco` se Python, Node.js, Docker install karega.<br>2. VS Code extensions install karega (Python, JS/TS, Docker).<br>3. `pip install -r requirements.txt` run karega.<br>4. `npm install` run karega.<br>5. `.env.example` se `.env` generate karega.<br>6. Sab installations verify karega (`python --version`, `node --version`).<br>7. `complete_task` call karega with installation log. |

---

## 🚀 Getting Started

### 1. System Prerequisites

- **OS:** Windows 10/11 (Required for full Win32/Registry protocol features)
- **Python:** `>= 3.10`
- **Node.js:** `>= 18.0` (Required for WhatsApp Baileys background service)
- **Git:** Latest stable release
- **Microphone:** For voice mode
- **Local Assets:**
  - `Data/model/Jarvis.onnx` — Custom openWakeWord model
  - `Bin/InputPopup.exe` and `Bin/SttPopup.exe` — Optional but required for native popups

### 2. Quick Install

```powershell
# Clone the repository
git clone https://github.com/thekaifansari01/jarvis-by-kaif-ansari.git
cd jarvis-by-kaif-ansari

# Create and activate a Python Virtual Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install required Python dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Install Node.js dependencies for WhatsApp Service
npm install
npm --prefix tools/Messanger/whatsapp/BaileysServer install
```

### 3. Register Desktop URI Protocol (OAuth)

To enable seamless OAuth web-authentication for Gmail and Google Calendar (`jarvis://` callback), run:

```powershell
python SetupRegistry.py
```

### 4. WhatsApp Bridge Setup

On the first run, scan the QR code displayed by the Baileys process. Keep the local service private; it is intended only for this machine.

- Local service URL: `http://localhost:3000`
- Session data: `Data/SessionCookies/auth_info_baileys/`

### 5. WhatsApp Contacts (Optional)

Create `Data/contacts.json` for named recipients:

```json
{
  "kaif": "919876543210",
  "work": "911234567890"
}
```

---

## ⚙️ Configuration & Enterprise Security

Create a `.env` file in your root project directory:

```powershell
Copy-Item .env.example .env
```

### Full Environment Variables & Hidden Configs (`config.py`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | FastBrain & Summarization API. | (Required) |
| `GEMINI_API_KEY` | Embeddings, Vision, Reasoning. | (Required) |
| `REGOLO_API_KEY` | Agentic Primary Provider. | (Required) |
| `OPENROUTER_API_KEY` | Fallback Agentic Provider. | (Optional) |
| `TAVILY_API_KEY` | Web search tool. | (Required for search) |
| `DEEPGRAM_API_KEY` | Live speech-to-text. | (Required for voice) |
| `TOGETHER_AI` | FLUX image-generation fallback. | (Optional) |
| `AGENT_PRIMARY_PROVIDER` | Choose `regolo`, `gemini`, or `openrouter`. | `regolo` |
| `AGENT_FALLBACK_PROVIDER` | Auto-fallback when primary fails. | `gemini` |
| `EMBEDDING_DIM` | Dimension for ChromaDB vectors. | `768` |
| `DEEP_RESEARCH_TIMEOUT` | Max seconds for deep research synthesis. | `420` |
| `AGENT_MAX_STEPS` | Max agent loop iterations. | `50` |
| `AGENT_TIMEOUT` | Max seconds for agent loop. | `1800` |
| `AGENT_RETRY_LIMIT` | Retries on tool failure before abort. | `2` |

> **Security Note:** Never commit your `.env` or `Data/SessionCookies/` directory to public version control. They are excluded via `.gitignore` by default.

---

## 🎮 Running JARVIS

### 1. Full Autonomous Voice & Desktop Mode (Default)

```powershell
python main.py
```

This starts the agent panel, STT popup (when the binary exists), Baileys bridge, service watchdog, RAG engine, proactive listeners, global hotkey, and wake-word listener.

### 2. Silent Mode (Wake Word Disabled, Trigger via Hotkeys Only)

```powershell
python main.py no_wake
```

This disables only the wake-word listener. The agent panel, background services, proactive listeners, and `Ctrl + Shift + J` hotkey still start.

### 3. Development Bootstrap Mode

```powershell
python main.py test_jarvis
```

This mode skips the one-second startup delay. It does **not** disable STT, Baileys, the agent panel, RAG, or proactive services. Combine it with `no_wake` if you do not want wake-word listening.

### 4. Stop JARVIS

- Say `exit`, `quit`, `stop`, or `bye` after voice activation, or
- Press `Ctrl + C` in the terminal running JARVIS.

### Keyboard Shortcuts

- `Ctrl + Shift + J`: Open Floating Text Input & Markdown UI Popup (Runs `InputPopup.exe`).

---

## 📂 Repository Anatomy

```
jarvis-by-kaif-ansari/
├── Bin/                           # Compiled Executables
│   ├── InputPopup.exe             # Text input UI (Hotkey trigger)
│   └── SttPopup.exe               # Voice status floating indicator
├── core/
│   ├── brain/
│   │   ├── Processor/             # Routing & Intelligence
│   │   │   ├── Processor.py       # RegoloSemanticRouter + Local Fallback
│   │   │   ├── FastBrain.py       # Groq LPU integration (Stateless)
│   │   │   ├── AgenticBrain.py    # Agent Loop, 4-Pillar Contract, Two-Strike
│   │   │   └── Prompts.py         # System Prompts & Safety Contracts
│   │   ├── Providers/             # Multi-LLM Abstraction Layer
│   │   │   ├── baseProvider.py    # Abstract Class
│   │   │   ├── regoloProvider.py
│   │   │   ├── geminiProvider.py
│   │   │   └── openrouterProvider.py
│   │   ├── Memory/                # Persistence Ecosystem
│   │   │   ├── Memory.py          # JSONL Context, User Bio/Mood, LTM Archiver
│   │   │   ├── LifetimeMemory.py  # ChromaDB Episodic Memory (Daily Summaries)
│   │   │   └── RagEngine.py       # Smart Chunking, Hash-based RAG Indexing
│   │   ├── executor.py            # Tool Dispatcher (System, File, Comms)
│   │   └── config.py              # Enterprise Configurations
│   ├── main/
│   │   ├── CommandHandler.py      # Main command bus, _is_busy state
│   │   ├── HotKeyManager.py       # Ctrl+Shift+J binding
│   │   ├── BackgroundServices.py  # Spawn/Kill STT, Baileys, Agent Panel
│   │   └── ServiceWatchdog.py     # Auto-Restart daemon for background processes
│   ├── voice/                     # STT, TTS, Wake Word
│   │   ├── stt.py (Deepgram)
│   │   ├── tts.py (Edge TTS)
│   │   └── stt_status.py          # Popup visibility controller
│   ├── ui/                        # PyQt5 UI Suite
│   │   ├── agent_panel.py         # ZMQ-based floating status panel
│   │   ├── agent_status.py        # ZMQ publisher for agent updates
│   │   ├── typing_status.py       # JSON file writer for typing popup
│   │   └── Popup/                 # Markdown rendering popup
│   │       ├── Popup.py           # Entry point
│   │       ├── PopupUI.py         # Main UI (glass-morphism, resize, animations)
│   │       ├── AsyncBrowser.py    # Async image loading, cache, preview engine
│   │       └── TextParser.py      # Background markdown parser, syntax highlighter
│   └── utils/
│       ├── utils.py               # resolve_pronouns, helpers
│       └── ProcessManager.py      # Safe subprocess tree spawning/killing
├── tools/
│   ├── Messanger/                 # Gmail Pub/Sub & Baileys WhatsApp
│   │   └── whatsapp/BaileysServer/ (Node.js)
│   ├── SystemTools/               # Win32 OS controls, File Editor
│   │   ├── fileEditor.py          # repo_map, replace_block, create_many
│   │   └── clipboard_tool.py      # OS Clipboard CRUD
│   ├── SearchTools/               # Tavily, ArXiv, DeepResearch
│   ├── Vision/                    # Multimodal image/video handlers
│   └── ImageGeneration/           # Text-to-image, image-to-image
├── Proactive/                     # HITL Scout & Event Queue
│   ├── proactive_agent.py
│   ├── Email/                     # Gmail Pub/Sub listener
│   ├── WhatsApp/                  # WhatsApp alert listener
│   └── Reminders/                 # Calendar reminder listener
├── Data/                          # Local State (Vectors, Profile, Cookies)
│   ├── jarvis_memory/             # ChromaDB LTM & JSONL history
│   └── SessionCookies/            # Baileys creds, OAuth tokens
├── fonts/                         # UI fonts (English, Devanagari)
├── SetupRegistry.py               # Registers jarvis:// URI protocol
├── main.py                        # Primary Entry Point
└── requirements.txt               # Production dependencies
```

---

## 🔧 Troubleshooting

| Problem | Checks and Fix |
| :--- | :--- |
| `ModuleNotFoundError` on startup | Activate `.venv`, run `pip install -r requirements.txt`. |
| `openwakeword` / ONNX error | Confirm `Data/model/Jarvis.onnx` exists. |
| Wake word starts but speech is not transcribed | Set `DEEPGRAM_API_KEY`, allow microphone access in Windows. |
| Gmail/Calendar sign-in does not finish | Run `python SetupRegistry.py`, check `API_BASE_URL`, retry browser flow. |
| WhatsApp cannot send | Run both `npm install` commands, complete QR login, ensure port 3000 is free. |
| Agent panel/STT/Input popup is absent | Ensure the relevant executable exists in `Bin/`; otherwise build from `core/UiSrc/`. |
| RAG returns no results | Put supported files in `Documents/Jarvis/RAG/`, set `GEMINI_API_KEY`, allow background indexer time. |
| Need diagnostic information | Read `Data/jarvis.log` — console also prints service/tool errors. |

---

## 🤝 Contributing

1. **Fork** the repository.
2. **Create** a feature branch (`git checkout -b feature/AdvancedTooling`).
3. **Commit** your changes with clear, descriptive messages.
4. **Push** to your fork (`git push origin feature/AdvancedTooling`).
5. **Open** a Pull Request for review.

> **Note:** Do not commit `.env`, `Data/SessionCookies/`, generated media, or local memory. They are excluded via `.gitignore`.

---

## 📄 License

This project is released under the **MIT License** — see the [LICENSE](LICENSE) file for complete details.

---

<div align="center">

**Built with ❤️ and pragmatic engineering by Kaif Ansari**

*If this project inspired your own AI architecture, consider leaving a ⭐ on the repository!*

</div>