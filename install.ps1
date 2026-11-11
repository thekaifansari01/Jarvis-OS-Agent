# ==========================================
# J.A.R.V.I.S. OS Agent - Production Installer
# ==========================================

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.ForegroundColor = "Cyan"
Clear-Host

Write-Host @"
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
   Automated Installer for Windows (v1.0)
"@ -ForegroundColor Cyan

Write-Host "`n[1/6] Checking Prerequisites..." -ForegroundColor Yellow

# Check Git
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Git is not installed. Please install Git from https://git-scm.com/download/win" -ForegroundColor Red
    exit
}

# Check Python (Must be 3.10+)
$pyVersion = & python -c "import sys; print(sys.version_info.major == 3 and sys.version_info.minor >= 10)" 2>$null
if ($pyVersion -ne "True") {
    Write-Host "❌ Python 3.10+ is required. Current version is missing or outdated. Download from https://www.python.org/downloads/" -ForegroundColor Red
    exit
}

# Check Node.js (Must be 18+)
if (!(Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js is not installed. Please install Node.js 18+ from https://nodejs.org/" -ForegroundColor Red
    exit
}

Write-Host "✅ All prerequisites met (Git, Python 3.10+, Node.js)." -ForegroundColor Green

# Step 2: Clone Repo into User's Home Directory
Write-Host "`n[2/6] Cloning J.A.R.V.I.S. Repository..." -ForegroundColor Yellow

# Define install location safely in the user's home folder
$installPath = Join-Path $HOME "Jarvis-OS-Agent"

if (Test-Path $installPath) {
    Write-Host "⚠️ Folder already exists at $installPath. Updating..." -ForegroundColor DarkYellow
    Set-Location -Path $installPath
    git pull
} else {
    Write-Host "📁 Installing to: $installPath" -ForegroundColor Cyan
    git clone https://github.com/thekaifansari01/Jarvis-OS-Agent.git $installPath
    Set-Location -Path $installPath
}

# Step 3: Python Virtual Environment
Write-Host "`n[3/6] Setting up Python Virtual Environment..." -ForegroundColor Yellow
if (!(Test-Path ".venv")) {
    python -m venv .venv
} else {
    Write-Host "⚠️ .venv already exists. Skipping creation." -ForegroundColor DarkYellow
}

$pythonExe = ".\\.venv\\Scripts\\python.exe"
$pipExe = ".\\.venv\\Scripts\\pip.exe"

# Step 4: Install Python Dependencies
Write-Host "`n[4/6] Installing Python Dependencies (This may take 5-10 minutes)..." -ForegroundColor Yellow
Write-Host "⚠️ PyTorch CPU and heavy AI models are being installed. Please wait..." -ForegroundColor DarkGray

& $pythonExe -m pip install --upgrade pip
# Installing requirements directly uses the --extra-index-url for PyTorch CPU
& $pipExe install -r requirements.txt
# Ensure MCP is installed (it's in requirements, but just to be safe)
& $pipExe install mcp

# Step 5: Install Node.js Dependencies (WhatsApp Baileys)
Write-Host "`n[5/6] Installing Node.js dependencies for WhatsApp Bridge..." -ForegroundColor Yellow
Set-Location -Path "tools\Messanger\whatsapp\BaileysServer"
npm install
Set-Location -Path "..\..\..\..\"

# Step 6: Environment & Registry Setup
Write-Host "`n[6/6] Finalizing Setup..." -ForegroundColor Yellow

# Auto-create .env if it doesn't exist
if (!(Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item -Path ".env.example" -Destination ".env"
        Write-Host "✅ Created .env from .env.example" -ForegroundColor Green
    } else {
        Write-Host "⚠️ .env.example not found! You will need to create .env manually." -ForegroundColor DarkYellow
    }
}

# Register the 'jarvis' command globally
& $pythonExe SetupRegistry.py

# Success Message
Write-Host "`n===============================================" -ForegroundColor Green
Write-Host "🎉 J.A.R.V.I.S. Installed Successfully!" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host "To launch Jarvis, simply close this terminal," -ForegroundColor White
Write-Host "open a NEW PowerShell or Command Prompt and type:" -ForegroundColor White
Write-Host "`n   jarvis`n" -ForegroundColor Cyan
Write-Host "⚠️ IMPORTANT: Open the '.env' file in the folder and add your API keys!" -ForegroundColor Yellow
Write-Host "===============================================`n" -ForegroundColor Green