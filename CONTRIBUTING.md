# 🤝 Contributing to Jarvis-OS-Agent

First off, thank you for considering contributing to Jarvis-OS-Agent! 🚀  
It's people like you that make open-source so special. Whether it's a bug report, feature suggestion, or a pull request, all contributions are welcome.

We follow the **"Do the right thing"** principle — if it makes Jarvis faster, smarter, or easier to use, we want it.

---

## 📜 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). We expect all contributors to be respectful and inclusive.

---

## 🛠️ What You Can Contribute

| Type | Description |
| :--- | :--- |
| 🐛 **Bug Fixes** | Found a crash? Fix it and send a PR. |
| ✨ **New Features** | New provider (e.g., Anthropic Claude)? New tool (e.g., Spotify control)? Let's add it! |
| 📚 **Documentation** | Typos, outdated README sections, or new examples. |
| 🧪 **Tests** | Unit tests, integration tests, or test scenarios. |
| 🎨 **UI/UX** | Agent panel styling, popup improvements, or new status indicators. |

---

## 🚀 Getting Started (Development Setup)

Follow these steps to set up the project locally for development:

### 1. Fork & Clone
```powershell
# Fork the repo on GitHub, then clone YOUR fork
git clone https://github.com/thekaifansari01/Jarvis-OS-Agent.git
cd Jarvis-OS-Agent
```

### 2. Python Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Node.js Dependencies (for WhatsApp)
```powershell
cd tools/Messanger/whatsapp/BaileysServer
npm install
cd ../../../../  # Return to root
```

### 4. Environment Setup
```powershell
# Copy the example env file
Copy-Item .env.example .env
# Open .env and fill in your API keys (Groq, Gemini, etc.)
```

### 5. Global CLI Registration (Optional for Testing)
```powershell
# Run this once to test the 'jarvis' command globally
python SetupRegistry.py
```

---

## 🧑‍💻 Coding Standards

We try to keep the code clean and consistent. Please follow these guidelines:

- **Python:** Follow **[PEP 8](https://peps.python.org/pep-0008/)** . Use `snake_case` for functions/variables and `PascalCase` for classes.
- **Line Length:** Keep lines to **88 characters** (we use Black/PEP 8 recommendations).
- **Imports:** Group imports in the order: Standard Library → Third-Party → Local Modules.
- **String Formatting:** Use f-strings over `%` or `.format()` where possible.
- **No Emojis in Code:** Avoid emojis (`✅`, `❌`, `🔥`) inside `run_python_code` print statements. Use plain tags like `[SUCCESS]`, `[ERROR]` instead (Windows console compatibility).
- **Windows Paths:** Always use forward slashes (`/`) in file paths. Use `os.path.abspath()` to resolve. Avoid raw backslashes (`\\`).

---

## 📝 Commit Message Guidelines

Write clear, meaningful commit messages so we know exactly what changed.

**Format:** `type(scope): Subject`

| Type | When to use |
| :--- | :--- |
| `feat` | A new feature. |
| `fix` | A bug fix. |
| `docs` | Documentation changes. |
| `style` | Code style (formatting, missing semicolons, etc). No logic change. |
| `refactor` | Code rewrite without changing external behavior. |
| `test` | Adding or fixing tests. |
| `chore` | Build process, config changes, etc. |

**Examples:**
- `feat(tools): Add support for custom OpenAI provider`
- `fix(agent): Resolve memory leak in LTM archiver`
- `docs(readme): Update installation steps for Windows 11`

---

## 🔀 Pull Request Process

1. **Sync your fork:** Before starting, make sure your `main` branch is up to date.
   ```powershell
   git checkout main
   git pull upstream main
   ```

2. **Create a feature branch:**
   ```powershell
   git checkout -b feature/your-awesome-feature
   ```

3. **Write your code.** Add tests if applicable.

4. **Test your changes locally:**
   ```powershell
   # Run the agent in test mode to ensure nothing breaks
   python main.py test_jarvis
   ```

5. **Commit your changes** (using the commit guidelines above).

6. **Push to your fork:**
   ```powershell
   git push origin feature/your-awesome-feature
   ```

7. **Open a Pull Request** on the main repository:
   - Provide a clear title and description.
   - Link any related issues (e.g., `Closes #123`).
   - Check the "Allow edits from maintainers" checkbox.

### ✅ PR Checklist
Before submitting, please ensure:
- [ ] My code follows the style guidelines of this project.
- [ ] I have performed a self-review of my own code.
- [ ] I have commented my code, particularly in hard-to-understand areas.
- [ ] I have made corresponding changes to the documentation (README, Wiki).
- [ ] My changes generate no new warnings or errors.
- [ ] I have tested my changes on **Windows 10/11** (Primary platform).

---

## 🐛 Reporting Bugs

Please use the **Bug Report template** when creating issues on GitHub. It helps us fix things much faster.

Make sure to include:
- Your Windows version.
- Python version.
- The exact command you ran.
- Relevant logs from `Data/jarvis.log` (Remember to redact API keys!).

---

## 💬 Community & Support

- Use the **GitHub Discussions** tab for Q&A, ideas, or general queries.
- For urgent issues, tag `@thekaifansari01` in your issue.

---

## 🎉 Final Thank You

Every contribution, no matter how small, makes a difference. You're not just writing code — you're helping build the future of open-source AI agents.

**Let's build something legendary together!** ☕️🚀
