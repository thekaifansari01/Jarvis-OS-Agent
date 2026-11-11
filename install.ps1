$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host ""
    Write-Host "[$Step] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [!] $Message" -ForegroundColor DarkYellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [X] $Message" -ForegroundColor Red
}

function Update-SessionPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Get-ValidPython {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found -and ($found.Source -notmatch "WindowsApps")) {
            if ($cmd -eq "py") {
                $check = & py -3 -c "import sys; print(1 if (sys.version_info.major == 3 and sys.version_info.minor >= 10) else 0)" 2>$null
                if ($LASTEXITCODE -eq 0 -and "$check".Trim() -eq "1") {
                    $exePath = & py -3 -c "import sys; print(sys.executable)" 2>$null
                    if ($exePath -and (Test-Path "$exePath".Trim())) {
                        return "$exePath".Trim()
                    }
                }
            } else {
                $check = & $found.Source -c "import sys; print(1 if (sys.version_info.major == 3 and sys.version_info.minor >= 10) else 0)" 2>$null
                if ($LASTEXITCODE -eq 0 -and "$check".Trim() -eq "1") {
                    return $found.Source
                }
            }
        }
    }
    $localPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($p in $localPaths) {
        if (Test-Path $p) {
            return $p
        }
    }
    return $null
}

function Test-NodeVersion {
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $nodeCmd -or -not $npmCmd) {
        return $false
    }
    $ver = & node -e "console.log(process.versions.node.split('.')[0])" 2>$null
    if ($LASTEXITCODE -eq 0 -and ($ver -as [int]) -ge 18) {
        return $true
    }
    return $false
}

function Install-WithWinget {
    param([string]$PackageId, [string]$DisplayName)
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }
    Write-Host "  -> Auto-installing $DisplayName via winget..." -ForegroundColor Cyan
    & winget install --id $PackageId -e --source winget --accept-package-agreements --accept-source-agreements --silent
    Update-SessionPath
    return ($LASTEXITCODE -eq 0)
}

function Set-EnvValue {
    param([string]$FilePath, [string]$Key, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return
    }
    $content = Get-Content -Path $FilePath -Raw
    $pattern = "(?m)^" + [regex]::Escape($Key) + "\s*=.*$"
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, "$Key=$Value")
    } else {
        $content = $content.TrimEnd() + "`r`n$Key=$Value`r`n"
    }
    Set-Content -Path $FilePath -Value $content -Encoding UTF8
}

function Install-Jarvis {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "   J.A.R.V.I.S. OS Agent - Production Automated Setup     " -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

    Write-Step "1/6" "Verifying System Prerequisites..."
    Update-SessionPath

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Warn "Git not found."
        if (-not (Install-WithWinget -PackageId "Git.Git" -DisplayName "Git")) {
            Write-Fail "Git is required. Install from https://git-scm.com/download/win and re-run."
            return
        }
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Fail "Git executable still not detected in PATH. Please restart PowerShell and try again."
        return
    }
    Write-Success "Git detected."

    $sysPython = Get-ValidPython
    if (-not $sysPython) {
        Write-Warn "Python 3.10+ not found."
        if (Install-WithWinget -PackageId "Python.Python.3.11" -DisplayName "Python 3.11") {
            $sysPython = Get-ValidPython
        }
        if (-not $sysPython) {
            Write-Fail "Python 3.10+ is required. Install from https://www.python.org/downloads/ (check 'Add to PATH')."
            return
        }
    }
    $pyVerStr = & $sysPython --version 2>&1
    Write-Success "Python detected ($pyVerStr)."

    if (-not (Test-NodeVersion)) {
        Write-Warn "Node.js 18+ not found."
        if (-not (Install-WithWinget -PackageId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS")) {
            Write-Fail "Node.js 18+ is required. Install from https://nodejs.org/ and re-run."
            return
        }
        if (-not (Test-NodeVersion)) {
            Write-Fail "Node.js 18+ installation could not be verified. Please restart PowerShell and re-run."
            return
        }
    }
    $nodeVerStr = & node --version 2>&1
    Write-Success "Node.js detected ($nodeVerStr)."

    Write-Step "2/6" "Syncing J.A.R.V.I.S. OS Agent Repository..."
    $installPath = Join-Path $HOME "Jarvis-OS-Agent"
    $repoUrl = "https://github.com/thekaifansari01/Jarvis-OS-Agent.git"

    if (Test-Path (Join-Path $installPath ".git")) {
        Write-Host "  -> Existing repository found at $installPath. Fetching updates..." -ForegroundColor Cyan
        Push-Location $installPath
        try {
            & git fetch origin main 2>&1 | Out-Null
            & git pull --ff-only origin main
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Local modifications detected. Preserving local working tree."
            } else {
                Write-Success "Repository updated to latest commit."
            }
        } finally {
            Pop-Location
        }
    } else {
        if (Test-Path $installPath) {
            $backupPath = "${installPath}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-Warn "Non-git folder exists at $installPath. Moving to $backupPath..."
            Move-Item -Path $installPath -Destination $backupPath -Force
        }
        Write-Host "  -> Cloning into $installPath..." -ForegroundColor Cyan
        & git clone --depth 1 $repoUrl $installPath
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $installPath "requirements.txt"))) {
            Write-Fail "Failed to clone repository. Check your internet connection."
            return
        }
        Write-Success "Repository cloned successfully."
    }

    Push-Location $installPath
    try {
        Write-Step "3/6" "Configuring Isolated Python Virtual Environment (.venv)..."
        $venvPython = Join-Path $installPath ".venv\Scripts\python.exe"

        if (Test-Path $venvPython) {
            & $venvPython -c "import sys" 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Existing .venv appears corrupted. Recreating..."
                Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        if (-not (Test-Path $venvPython)) {
            & $sysPython -m venv .venv
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
                Write-Fail "Failed to create Python virtual environment."
                return
            }
            Write-Success "Virtual environment created."
        } else {
            Write-Success "Healthy virtual environment already exists."
        }

        Write-Step "4/6" "Installing Python Dependencies & AI Models (5-10 mins on first run)..."
        Write-Host "  -> Upgrading pip, setuptools, and wheel..." -ForegroundColor DarkGray
        & $venvPython -m pip install --upgrade pip setuptools wheel --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Pip self-upgrade reported a warning; continuing with dependency installation..."
        }

        Write-Host "  -> Installing packages from requirements.txt (CPU-optimized PyTorch)..." -ForegroundColor DarkGray
        & $venvPython -m pip install --prefer-binary -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Python dependency installation failed. Check the error output above."
            return
        }
        Write-Success "All Python packages installed and verified."

        Write-Step "5/6" "Installing Node.js Dependencies for WhatsApp Baileys Bridge..."
        $baileysPath = Join-Path $installPath "tools\Messanger\whatsapp\BaileysServer"
        if (Test-Path $baileysPath) {
            Push-Location $baileysPath
            try {
                & npm install --no-audit --no-fund
                if ($LASTEXITCODE -ne 0) {
                    Write-Fail "npm install failed inside BaileysServer."
                    return
                }
                Write-Success "WhatsApp Baileys Bridge dependencies installed."
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "BaileysServer directory not found; skipping npm install."
        }

        Write-Step "6/6" "Finalizing Environment & Registering Global 'jarvis' CLI..."
        $envFile = Join-Path $installPath ".env"
        $envExample = Join-Path $installPath ".env.example"

        if (-not (Test-Path $envFile)) {
            if (Test-Path $envExample) {
                Copy-Item -Path $envExample -Destination $envFile -Force
                Write-Success "Initialized .env from .env.example."
            } else {
                New-Item -ItemType File -Path $envFile -Force | Out-Null
                Write-Warn "Created empty .env file (.env.example was not found)."
            }
        } else {
            Write-Success "Existing .env configuration preserved."
        }

        & $venvPython SetupRegistry.py
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "SetupRegistry.py returned a non-zero exit code."
        } else {
            Update-SessionPath
            Write-Success "Global 'jarvis' command registered and activated for current session."
        }

        if ([Environment]::UserInteractive) {
            Write-Host ""
            $configureNow = Read-Host "Would you like to configure your core API keys right now? (y/N)"
            if ($configureNow -match "^[Yy]") {
                Write-Host ""
                Write-Host "Press Enter to skip any key you want to configure later in .env" -ForegroundColor DarkGray
                $groqKey = Read-Host "  1. Enter Groq / Primary LLM API Key"
                $deepgramKey = Read-Host "  2. Enter Deepgram API Key (Voice STT)"
                $tavilyKey = Read-Host "  3. Enter Tavily API Key (Web Search)"

                if (-not [string]::IsNullOrWhiteSpace($groqKey)) {
                    Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "ROUTER_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "MEMORY_SUMMARY_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "PROACTIVE_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "PRIMARY_API_KEY" -Value $groqKey.Trim()
                    Set-EnvValue -FilePath $envFile -Key "FALLBACK_API_KEY" -Value $groqKey.Trim()
                }
                if (-not [string]::IsNullOrWhiteSpace($deepgramKey)) {
                    Set-EnvValue -FilePath $envFile -Key "DEEPGRAM_API_KEY" -Value $deepgramKey.Trim()
                }
                if (-not [string]::IsNullOrWhiteSpace($tavilyKey)) {
                    Set-EnvValue -FilePath $envFile -Key "TAVILY_API_KEY" -Value $tavilyKey.Trim()
                }
                Write-Success "API keys saved to $envFile"
            }
        }

        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "      J.A.R.V.I.S. OS Agent Installed Successfully!       " -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "  Install Location : $installPath" -ForegroundColor White
        Write-Host "  Config File      : $envFile" -ForegroundColor White
        Write-Host "  Launch Command   : jarvis" -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host ""
    } finally {
        Pop-Location
    }
}

Install-Jarvis