# 🧠 JARVIS AI Assistant – Complete System Blueprint

> **Version:** 3.1 (Mindly Core)  
> **Architecture:** Hybrid Router + Agentic Loop + Fast Brain  
> **Platform:** Windows-first, cross-platform compatible  

[![GitHub repo](https://img.shields.io/badge/GitHub-thekaifansari01%2Fjarvis--by--kaif--ansari-blue?logo=github)](https://github.com/thekaifansari01/jarvis-by-kaif-ansari)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-orange)](https://groq.com)
[![Gemini](https://img.shields.io/badge/Gemini-1M_context-blue)](https://deepmind.google/technologies/gemini/)

## 📖 Overview

**JARVIS** is a voice‑first, multimodal AI assistant that combines the speed of Groq’s Llama 3.3 with the reasoning power of Gemini’s agentic loops. It can control your PC, manage emails, search the web, generate images, conduct deep research, and maintain a long‑term memory – all through natural Hinglish (Roman script) or English commands.

> **“Jarvis, kaal ki meeting ka email Kaif ko bhej do.”**  
> *Assistant sends an email, schedules follow‑ups, and speaks back in milliseconds.*

---

## ✨ Key Features

| Category | Capabilities |
|----------|---------------|
| **Voice** | Wake word (“Jarvis”) – Porcupine, real‑time STT (Deepgram Nova‑2), streaming TTS (Cartesia / Edge TTS fallback) with emotion detection |
| **Fast Actions** | Open/close apps (fuzzy matching, registry cache), control volume/brightness, lock/sleep PC, open URLs, YouTube search |
| **Agentic Tasks** | Send emails (Gmail API), WhatsApp messages, read/write workspace files, screen capture + vision analysis, clipboard control |
| **Search & Research** | Web search (Tavily), arXiv papers, YouTube transcripts, webpage scraping (Jina Reader), autonomous deep research (Gemini, multi‑step) |
| **Memory** | ChromaDB embeddings for chat history + workspace RAG (semantic file search), user bio/preferences, mood tracking, long‑term summaries |
| **Image Generation** | FLUX (Together AI) – 4‑step instant generation, AI Horde img2img editing |
| **UI** | Rich terminal (Claude‑style), floating STT popup (Dynamic Island), agent thought panel (PyQt5), system tray, global hotkey (Ctrl+Shift+J) |
| **Workspace** | `Jarvis_Workspace/` with Vault (RAG), Creations (outputs), Temp (auto‑cleaned), registry.json for instant file lookups |

---

## 🏗 Architecture

```
User Input (Voice / Text)
       │
       ▼
┌──────────────┐     FAST (70%)      ┌─────────────────┐
│ Smart Router │ ─────────────────► │   Fast Brain     │
│ (Groq 8B)    │                     │ (Groq Llama 3.3) │
└──────────────┘                     │ + tool call      │
       │                             └────────┬────────┘
       │ AGENTIC (30%)                        │
       ▼                                      ▼
┌──────────────┐                     ┌─────────────────┐
│ Agentic Brain│ ◄────────────────── │ execute_actions │
│ (Gemini 31B) │                     │ (async / sync)  │
│ 13 tools     │                     └────────┬────────┘
└──────────────┘                              │
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
              ┌───────────────┐
              │  Tools Layer  │
              │ (Search, Mail,│
              │ Workspace,    │
              │ System, etc.) │
              └───────────────┘
```

### Core Decision Flow
1. **Router** decides if command is **FAST** (app open, stateless chat) or **AGENTIC** (email, web research, file ops).
2. **Fast Brain** (Groq 70B) uses native `system_controller` tool – response in <1s.
3. **Agentic Brain** (Gemini 31B) runs up to 20 tool‑calling steps, updates UI, handles follow‑ups.
4. **Executor** runs actions in thread pool, streams TTS, and logs everything.

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| **LLM (Fast)** | Groq – Llama 3.3 70B / Router 8B |
| **LLM (Agentic)** | Gemini – Gemma 4 31B (1M context) |
| **Embeddings** | Gemini Embedding 2 (768d) |
| **Vector DB** | ChromaDB (separate for chat & RAG) |
| **STT** | Deepgram Nova‑2 (websocket, Hindi+English) |
| **Wake Word** | Porcupine (offline) |
| **TTS** | Cartesia Sonic‑3 (primary) / Edge TTS (fallback) |
| **Image** | Together AI (FLUX) + AI Horde (edit) |
| **Search** | Tavily, arXiv, YouTube Transcript, Jina Reader |
| **Email** | Gmail API (OAuth) |
| **WhatsApp** | pywhatkit / Twilio |
| **System** | psutil, pycaw, screen‑brightness‑control, pyautogui |
| **UI** | PyQt5, Rich, pystray, PIL |
| **Utilities** | python‑dotenv, keyboard, pyperclip |

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/thekaifansari01/jarvis-by-kaif-ansari.git
cd jarvis-by-kaif-ansari
```

### 2. Set up Python environment
```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
> **Note:** On Windows, also install `pywin32` for tray hiding.

### 4. Configure API keys
Copy `.env.example` to `.env` and fill in your keys:
```ini
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
TOGETHER_AI=your_together_key
TAVILY_API_KEY=your_tavily_key
PICOVOICE_API_KEY=your_picovoice_key
CARTESIA_API_KEY=your_cartesia_key   # optional
DEEPGRAM_API_KEY=your_deepgram_key
# ... etc
```

### 5. Set up Gmail OAuth (for email)
- Download `credentials.json` from Google Cloud Console → Gmail API.
- Place it in `Data/SessionCookies/credentials.json`.
- First email send will generate `token.json` automatically.

### 6. (Optional) Build app cache for faster app opening
The assistant builds a cache of installed apps in the background. No action needed.

---

## 🚀 Usage

### Start the assistant (voice mode)
```bash
python main.py
```
- Say **“Jarvis”** to wake.
- Speak your command (supports Hinglish / English).
- Watch the floating STT popup and agent panel.

### Text‑only mode (no microphone)
```bash
python main.py test_jarvis
```

### Force a specific TTS engine
```bash
python main.py voice=edge_tts
python main.py voice=cartesia
```

### Disable system tray (keep console always visible)
```bash
python main.py system_tray=no
```

### Global hotkey
Press **Ctrl+Shift+J** anywhere to open a floating text input popup – type your command and press Enter.

---

## 📁 Project Structure (Highlights)

```
jarvis-by-kaif-ansari/
├── main.py                    # Entry point
├── core/
│   ├── brain/                 # Memory, Router, Fast/Agentic brains, Executor
│   ├── voice/                 # STT, TTS, wake word, interrupt
│   ├── ui/                    # PyQt5 panels (agent_status, STT popup, input popup)
│   ├── terminal/              # Rich console + tray manager
│   └── utils/                 # ProcessManager, helper utils
├── tools/                     # All tool implementations
│   ├── OpenCloseApps/         # SmartAppOpener, close_any
│   ├── SearchTools/           # Web, Arxiv, YouTube, Scraper, DeepResearch
│   ├── Messanger/             # Email, WhatsApp, contact_book
│   ├── ImageGeneration/       # Flux + AI Horde
│   ├── SystemTools/           # clipboard, OS controls, screen capture
│   └── workspace/             # WorkspaceManager (vault/creations/temp)
├── Data/                      # ChromaDBs, JSON profiles, workspace folder
└── .env                       # API keys (ignored by git)
```

---

## ⚙️ Configuration

All major settings are in `core/brain/config.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_DIM` | 768 | Gemini embedding size |
| `AGENT_MAX_STEPS` | 20 | Max tool calls per agentic task |
| `AGENT_TIMEOUT` | 900s | Agent loop timeout |
| `DEEP_RESEARCH_TIMEOUT` | 420s | Deep research timeout |
| `COMMAND_HISTORY_LIMIT` | 10 | In‑memory command history |
| `ACTIVE_CONTEXT_WINDOW` | 120s | Auto‑relisten after wake word |

You can also override via CLI flags (see above).

---

## 🧠 Memory & RAG

- **Chat memory:** ChromaDB stores embeddings of all user messages. Semantic recall adds relevant past conversations to context.
- **User profile:** `user_bio.json`, `preferences.json`, `user_mood.json` – auto‑extracted by Groq 120B every few messages.
- **Workspace RAG:** Separate ChromaDB for files in `Vault/` and `Creations/`. Background indexing with MD5 hash cache.
- **Command history:** In‑memory deque – no disk I/O for speed.

---

## 🧪 Example Commands

| You say (Hinglish / English) | What happens |
|------------------------------|---------------|
| *“Jarvis, chrome khol”* | Opens Google Chrome (FAST path) |
| *“Volume 30 kar do”* | Sets system volume |
| *“YouTube pe Arijit Singh songs chala”* | Opens YouTube and searches |
| *“Kaif ko email bhej ki meeting kal hai”* | Agentic: looks up contact, sends email via Gmail |
| *“Deep research kar latest AI trends pe”* | Autonomous research (web + arXiv) → saves .md report |
| *“Screen capture karke bata isme kya likha hai”* | Captures screen, injects image into Gemini vision |
| *“Mera workspace vault search kar ‘budget’ ke liye”* | RAG search over your files |
| *“Ek image generate kar robot ka”* | FLUX generates PNG → opens in viewer |

---

## 🎤 Voice & Emotion

- **Wake word:** “Jarvis” – offline, low‑latency.
- **STT:** Deepgram Nova‑2 (supports Hindi + English code‑switching).
- **TTS:** Cartesia with emotion tags (anger, cheerful, sad, etc.). Fallback: Edge TTS.
- **Interruption:** Saying “Jarvis” while TTS is speaking cancels and re‑arms listening.

---

## 🖥️ UI Components

| Component | Description |
|-----------|-------------|
| **Rich Terminal** | Claude‑style orange theme, tree‑formatted logs, markdown rendering |
| **STT Popup** | Dynamic Island style (black pill, waveform) – shows live transcription |
| **Agent Panel** | Frameless PyQt5 window – shows thought, action, observation, step counter (auto‑hides) |
| **Input Popup** | Glassmorphic text input (Ctrl+Shift+J) |
| **System Tray** | Hide/show console, exit |

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again. |
| Wake word not working | Check `PICOVOICE_API_KEY` and microphone permissions. |
| Deepgram timeout | Ensure internet connection; try `test_jarvis` mode. |
| Gemini 429 quota | Free tier limit – wait 60 seconds or use Groq fallback. |
| Agent panel not showing | Kill any existing `agent_panel.py` process; main will respawn. |
| Image generation fails | Verify `TOGETHER_AI` key; for editing, AI Horde may have queue (speaks wait time). |

---

## 📜 License

[MIT](LICENSE) – feel free to use, modify, and contribute.

---

## 🙏 Credits

Developed by **Kaif Ansari** ([@thekaifansari01](https://github.com/thekaifansari01)).  
Built with Groq, Google Gemini, Cartesia, Deepgram, and many open‑source libraries.

> “Jarvis is not just an assistant – it’s a blueprint for hybrid, agentic AI on the desktop.”

---

## 🌟 Star the repo

If you find this project useful, please give it a ⭐ on GitHub!  
[![GitHub stars](https://img.shields.io/github/stars/thekaifansari01/jarvis-by-kaif-ansari?style=social)](https://github.com/thekaifansari01/jarvis-by-kaif-ansari)
