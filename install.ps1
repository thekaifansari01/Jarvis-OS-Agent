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

    $extraPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
        "$env:ProgramFiles\Python311",
        "$env:ProgramFiles\Python311\Scripts",
        "C:\Python311",
        "C:\Python311\Scripts",
        "$env:ProgramFiles\nodejs",
        "$env:APPDATA\npm",
        "$env:ProgramFiles\Git\cmd"
    )
    foreach ($p in $extraPaths) {
        if ((Test-Path $p) -and ($env:Path -notlike "*$p*")) {
            $env:Path = "$p;$env:Path"
        }
    }
}

function Download-FileFast {
    param([string]$Url, [string]$OutFile)
    if (Test-Path $OutFile) {
        Remove-Item -Path $OutFile -Force -ErrorAction SilentlyContinue
    }
    $curlCmd = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($curlCmd) {
        & $curlCmd.Source -fL --retry 3 --connect-timeout 15 -o $OutFile $Url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile)) {
            return $true
        }
    }
    $prevPref = $ProgressPreference
    try {
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -ErrorAction Stop
        return (Test-Path $OutFile)
    } catch {
        return $false
    } finally {
        $ProgressPreference = $prevPref
    }
}

function Test-IsPython311 {
    param([string]$ExePath)
    if ([string]::IsNullOrWhiteSpace($ExePath) -or -not (Test-Path $ExePath)) {
        return $false
    }
    if ($ExePath -match "WindowsApps") {
        return $false
    }
    $check = & $ExePath -c "import sys; print(1 if (sys.version_info.major == 3 and sys.version_info.minor == 11) else 0)" 2>$null
    return ($LASTEXITCODE -eq 0 -and "$check".Trim() -eq "1")
}

function Get-ValidPython {
    $knownPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "C:\Python311\python.exe",
        "${env:ProgramFiles(x86)}\Python311-32\python.exe"
    )
    foreach ($candidate in $knownPaths) {
        if (Test-IsPython311 -ExePath $candidate) {
            return $candidate
        }
    }

    $pyLauncher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $exePath = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exePath) {
            $trimmed = "$exePath".Trim()
            if (Test-IsPython311 -ExePath $trimmed) {
                return $trimmed
            }
        }
    }

    foreach ($cmd in @("python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found -and (Test-IsPython311 -ExePath $found.Source)) {
            return $found.Source
        }
    }

    $roots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:ProgramFiles",
        "C:\"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $dirs = Get-ChildItem -Path $root -Filter "Python311*" -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($dir in $dirs) {
            $exe = Join-Path $dir.FullName "python.exe"
            if (Test-IsPython311 -ExePath $exe) {
                return $exe
            }
        }
    }
    return $null
}

function Test-NodeVersion {
    Update-SessionPath
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCmd) {
        $fallback = "$env:ProgramFiles\nodejs\node.exe"
        if (Test-Path $fallback) {
            $env:Path = "$env:ProgramFiles\nodejs;$env:Path"
            $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
        }
    }
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $nodeCmd -or -not $npmCmd) {
        return $false
    }
    $ver = & $nodeCmd.Source -e "console.log(process.versions.node.split('.')[0])" 2>$null
    if ($LASTEXITCODE -eq 0 -and ($ver -as [int]) -ge 18) {
        return $true
    }
    return $false
}

function Get-LatestNodeMsiInfo {
    $prevPref = $ProgressPreference
    try {
        $ProgressPreference = "SilentlyContinue"
        $releases = Invoke-RestMethod -Uri "https://nodejs.org/dist/index.json" -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
        if ($releases -and $releases.Count -gt 0) {
            $latestVer = $releases[0].version.TrimStart("v")
            if (-not [string]::IsNullOrWhiteSpace($latestVer)) {
                return @{
                    Version = $latestVer
                    Url     = "https://nodejs.org/dist/v$latestVer/node-v$latestVer-x64.msi"
                }
            }
        }
    } catch {} finally {
        $ProgressPreference = $prevPref
    }
    $fallbackVer = "24.0.0"
    return @{
        Version = $fallbackVer
        Url     = "https://nodejs.org/dist/v$fallbackVer/node-v$fallbackVer-x64.msi"
    }
}

function Test-WingetAvailable {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { return $false }
    try {
        & winget --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Install-WithWinget {
    param(
        [string]$PackageId,
        [string]$DisplayName,
        [string]$Version = "",
        [switch]$UserScope
    )
    if (-not (Test-WingetAvailable)) {
        Write-Warn "winget not available on this system."
        return $false
    }

    Write-Host "  -> Auto-installing $DisplayName via winget..." -ForegroundColor Cyan
    $wingetArgs = @(
        "install", "--id", $PackageId, "-e",
        "--source", "winget",
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $wingetArgs += @("--version", $Version)
    }
    if ($UserScope) {
        $wingetArgs += @("--scope", "user")
    }

    & winget @wingetArgs
    $exit = $LASTEXITCODE

    if ($exit -ne 0 -and $exit -ne -1978335189) {
        Write-Warn "winget exited with code $exit for $DisplayName."
        return $false
    }

    Update-SessionPath
    return $true
}

function Stop-RunningJarvis {
    param([string]$TargetDir)
    if (-not (Test-Path $TargetDir)) { return }
    $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).ToLowerInvariant()
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant().StartsWith($normalizedTarget)) -or
        ($_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($normalizedTarget))
    }
    foreach ($proc in $processes) {
        if ($proc.ProcessId -ne $PID) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            } catch {}
        }
    }
}

function Set-EnvValue {
    param([string]$FilePath, [string]$Key, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return
    }
    $content = ""
    if (Test-Path $FilePath) {
        $raw = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
        if ($null -ne $raw) { $content = $raw }
    }
    $pattern = "(?m)^" + [regex]::Escape($Key) + "\s*=.*$"
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, "$Key=$Value")
    } else {
        if ([string]::IsNullOrWhiteSpace($content)) {
            $content = "$Key=$Value`r`n"
        } else {
            $content = $content.TrimEnd() + "`r`n$Key=$Value`r`n"
        }
    }
    Set-Content -Path $FilePath -Value $content -Encoding UTF8
}

function Clear-EnvValue {
    param([string]$FilePath, [string]$Key, [switch]$OnlyIfPlaceholder)
    if (-not (Test-Path $FilePath)) { return }
    $content = Get-Content -Path $FilePath -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrEmpty($content)) { return }
    $pattern = "(?m)^" + [regex]::Escape($Key) + "\s*=(.*)$"
    $m = [regex]::Match($content, $pattern)
    if (-not $m.Success) { return }
    $current = $m.Groups[1].Value.Trim()
    if ($OnlyIfPlaceholder -and $current -ne "your_key_here" -and $current -ne "your_key") { return }
    $content = [regex]::Replace($content, $pattern, "$Key=")
    Set-Content -Path $FilePath -Value $content -Encoding UTF8
}

function Get-EnvVal {
    param([string]$Content, [string]$Key)
    if ([string]::IsNullOrEmpty($Content)) { return "" }
    $m = [regex]::Match($Content, "(?m)^" + [regex]::Escape($Key) + "\s*=(.*)$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ""
}

function Read-EnvInput {
    param(
        [string]$Label,
        [string]$Default = "",
        [bool]$AllowSkip = $false
    )
    $prompt = "  $Label"
    if (-not [string]::IsNullOrWhiteSpace($Default)) {
        $prompt += " [default: $Default]"
    }
    $prompt += ": "
    while ($true) {
        $userInput = Read-Host $prompt
        if ([string]::IsNullOrWhiteSpace($userInput)) {
            if (-not [string]::IsNullOrWhiteSpace($Default)) { return $Default }
            if ($AllowSkip) { return $null }
            Write-Host "    [!] Value required." -ForegroundColor DarkYellow
            continue
        }
        $trimmed = $userInput.Trim()
        if ($AllowSkip -and ($trimmed -eq "s" -or $trimmed -eq "skip")) { return $null }
        return $trimmed
    }
}

function Read-YesNo {
    param(
        [string]$Question,
        [string]$Default = "N"
    )
    $hint = if ($Default -eq "Y") { "(Y/n)" } else { "(y/N)" }
    while ($true) {
        $ans = Read-Host "  $Question $hint"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
        $ans = $ans.Trim().ToLower()
        if ($ans -eq "y" -or $ans -eq "yes") { return "Y" }
        if ($ans -eq "n" -or $ans -eq "no") { return "N" }
        Write-Host "    [!] Please answer y or n." -ForegroundColor DarkYellow
    }
}

function Read-KeyWithReuse {
    param(
        [string]$GroupName,
        [string]$SourceKey,
        [string]$SourceEndpoint,
        [string]$SourceModel,
        [string]$DefaultEndpoint,
        [string]$DefaultModel
    )
    $reuse = Read-YesNo "Same as Fast Brain for $GroupName (key + endpoint + model)?" "Y"
    if ($reuse -eq "Y") {
        return @{ Key = $SourceKey; Endpoint = $SourceEndpoint; Model = $SourceModel }
    }
    return @{
        Key      = (Read-EnvInput "$GroupName API Key" "" $true)
        Endpoint = (Read-EnvInput "$GroupName Endpoint" $DefaultEndpoint)
        Model    = (Read-EnvInput "$GroupName Model" $DefaultModel)
    }
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
        Start-Sleep -Seconds 2
        Update-SessionPath
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Fail "Git executable still not detected in PATH. Please restart PowerShell and try again."
        return
    }
    Write-Success "Git detected."

    $sysPython = Get-ValidPython
    if (-not $sysPython) {
        Write-Warn "Python 3.11 not found. Auto-installing Python 3.11.4..."
        $pyVersion = "3.11.4"
        $pyInstaller = Join-Path $env:TEMP "python-$pyVersion-amd64.exe"
        $pyUrl = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-amd64.exe"

        Write-Host "  -> Downloading Python $pyVersion (~25 MB)..." -ForegroundColor Cyan
        if (Download-FileFast -Url $pyUrl -OutFile $pyInstaller) {
            Write-Host "  -> Running silent Python $pyVersion installer..." -ForegroundColor Cyan
            $proc = Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_launcher=1" -Wait -PassThru
            Remove-Item $pyInstaller -Force -ErrorAction SilentlyContinue
            Update-SessionPath
            Start-Sleep -Seconds 2
            $sysPython = Get-ValidPython
        } else {
            Write-Warn "Direct download of Python $pyVersion failed."
        }

        if (-not $sysPython -and (Test-WingetAvailable)) {
            Write-Warn "Attempting winget fallback for Python 3.11..."
            if (-not (Install-WithWinget -PackageId "Python.Python.3.11" -DisplayName "Python 3.11.4" -Version "3.11.4" -UserScope)) {
                Install-WithWinget -PackageId "Python.Python.3.11" -DisplayName "Python 3.11" -UserScope | Out-Null
            }
            Start-Sleep -Seconds 3
            Update-SessionPath
            $sysPython = Get-ValidPython
        }

        if (-not $sysPython) {
            Write-Fail "Python 3.11.4 could not be installed automatically."
            Write-Fail "Manual install: https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe"
            return
        }
    }
    $pyVerStr = & $sysPython --version 2>&1
    Write-Success "Python detected ($pyVerStr at $sysPython)."

    if (-not (Test-NodeVersion)) {
        Write-Warn "Node.js not found. Attempting auto-install of latest Node.js..."

        if (Test-WingetAvailable) {
            if (-not (Install-WithWinget -PackageId "OpenJS.NodeJS" -DisplayName "Node.js (Latest)")) {
                Install-WithWinget -PackageId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS" | Out-Null
            }
            Start-Sleep -Seconds 3
            Update-SessionPath
        }

        if (-not (Test-NodeVersion)) {
            Write-Warn "winget path failed or unavailable. Falling back to direct nodejs.org download..."
            $nodeInfo = Get-LatestNodeMsiInfo
            $nodeVer = $nodeInfo.Version
            $nodeUrl = $nodeInfo.Url
            $nodeMsi = Join-Path $env:TEMP "node-v$nodeVer-x64.msi"

            Write-Host "  -> Downloading Node.js v$nodeVer (~30 MB)..." -ForegroundColor Cyan
            if (Download-FileFast -Url $nodeUrl -OutFile $nodeMsi) {
                Write-Host "  -> Running Node.js installer (accept UAC prompt if shown)..." -ForegroundColor Cyan
                try {
                    Start-Process msiexec.exe -ArgumentList "/i", "`"$nodeMsi`"", "/passive", "/norestart" -Verb RunAs -Wait -ErrorAction Stop
                } catch {
                    Start-Process msiexec.exe -ArgumentList "/i", "`"$nodeMsi`"", "/qn", "/norestart" -Wait
                }
                Remove-Item $nodeMsi -Force -ErrorAction SilentlyContinue
                Update-SessionPath
                Start-Sleep -Seconds 2
            } else {
                Write-Warn "Direct Node.js download failed."
            }
        }

        if (-not (Test-NodeVersion)) {
            Write-Fail "Node.js could not be installed automatically."
            Write-Fail "Manual install: https://nodejs.org/ and re-run."
            return
        }
    }
    $nodeVerStr = & node --version 2>&1
    Write-Success "Node.js detected ($nodeVerStr)."

    Write-Step "2/6" "Syncing J.A.R.V.I.S. OS Agent Repository..."
    $installPath = Join-Path $HOME "Jarvis-OS-Agent"
    $repoUrl = "https://github.com/thekaifansari01/Jarvis-OS-Agent.git"

    Stop-RunningJarvis -TargetDir $installPath

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
        Write-Step "3/6" "Configuring Isolated Python 3.11 Virtual Environment (.venv)..."
        $venvPython = Join-Path $installPath ".venv\Scripts\python.exe"

        if (Test-Path $venvPython) {
            if (-not (Test-IsPython311 -ExePath $venvPython)) {
                Write-Warn "Existing .venv is broken or not running Python 3.11. Recreating with Python 3.11..."
                Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        if (-not (Test-Path $venvPython)) {
            & $sysPython -m venv .venv
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
                Write-Fail "Failed to create Python virtual environment."
                return
            }
            Write-Success "Python 3.11 virtual environment created."
        } else {
            Write-Success "Healthy Python 3.11 virtual environment already exists."
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
            $configureNow = Read-Host "Would you like to configure your API keys now? (y/N)"
            if ($configureNow -match "^[Yy]") {
                Write-Host ""
                Write-Host "  Press Enter to accept default; type 's' to skip any field." -ForegroundColor DarkGray
                Write-Host "  API_BASE_URL stays untouched (default is fine)." -ForegroundColor DarkGray

                $configuredCount = 0
                $skippedGroups = @()
                $warnings = @()

                Write-Host ""
                Write-Host "--- Identity ---" -ForegroundColor Cyan
                $userName = Read-EnvInput "Your name" "" $true
                if ($null -ne $userName) {
                    Set-EnvValue -FilePath $envFile -Key "USER_NAME" -Value $userName
                    Write-Success "USER_NAME set."
                    $configuredCount++
                } else {
                    Write-Warn "USER_NAME skipped."
                }

                Write-Host ""
                Write-Host "--- Fast Brain (MANDATORY) ---" -ForegroundColor Cyan
                $fbKey = Read-EnvInput "Fast Brain API Key (Groq/OpenAI-compatible)" "" $true
                $fbEndpoint = Read-EnvInput "Fast Brain Endpoint" "https://api.groq.com/openai/v1"
                $fbModel = Read-EnvInput "Fast Brain Model" "llama-3.3-70b-versatile"
                if ($null -ne $fbKey) {
                    Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_API_KEY" -Value $fbKey
                    Write-Success "FAST_BRAIN_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "FAST_BRAIN_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "FAST_BRAIN_API_KEY skipped (agent may NOT boot)."
                    $warnings += "FAST_BRAIN_API_KEY not configured"
                }
                Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_ENDPOINT" -Value $fbEndpoint
                Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_MODEL" -Value $fbModel

                Write-Host ""
                Write-Host "--- Semantic Router ---" -ForegroundColor Cyan
                $rtr = Read-KeyWithReuse "Router" $fbKey $fbEndpoint $fbModel "https://api.groq.com/openai/v1" "llama-3.3-70b-versatile"
                if ($null -ne $rtr.Key) {
                    Set-EnvValue -FilePath $envFile -Key "ROUTER_API_KEY" -Value $rtr.Key
                    Write-Success "ROUTER_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "ROUTER_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "ROUTER_API_KEY skipped."
                }
                Set-EnvValue -FilePath $envFile -Key "ROUTER_ENDPOINT" -Value $rtr.Endpoint
                Set-EnvValue -FilePath $envFile -Key "ROUTER_MODEL" -Value $rtr.Model

                Write-Host ""
                Write-Host "--- LTM Extraction ---" -ForegroundColor Cyan
                $ltm = Read-KeyWithReuse "LTM Extraction" $fbKey $fbEndpoint $fbModel "https://api.groq.com/openai/v1" "llama-3.3-70b-versatile"
                if ($null -ne $ltm.Key) {
                    Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_API_KEY" -Value $ltm.Key
                    Write-Success "LTM_EXTRACTION_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "LTM_EXTRACTION_API_KEY skipped."
                }
                Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_ENDPOINT" -Value $ltm.Endpoint
                Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_MODEL" -Value $ltm.Model

                Write-Host ""
                Write-Host "--- Proactive Agent ---" -ForegroundColor Cyan
                $pro = Read-KeyWithReuse "Proactive" $fbKey $fbEndpoint $fbModel "https://api.groq.com/openai/v1" "llama-3.3-70b-versatile"
                if ($null -ne $pro.Key) {
                    Set-EnvValue -FilePath $envFile -Key "PROACTIVE_API_KEY" -Value $pro.Key
                    Write-Success "PROACTIVE_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "PROACTIVE_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "PROACTIVE_API_KEY skipped."
                }
                Set-EnvValue -FilePath $envFile -Key "PROACTIVE_ENDPOINT" -Value $pro.Endpoint
                Set-EnvValue -FilePath $envFile -Key "PROACTIVE_MODEL" -Value $pro.Model

                Write-Host ""
                Write-Host "--- Agentic Brain: Primary ---" -ForegroundColor Cyan
                $priKey = Read-EnvInput "Primary API Key (OpenAI / any provider)" "" $true
                $priBase = Read-EnvInput "Primary Base URL" "https://api.openai.com/v1"
                $priModel = Read-EnvInput "Primary Model" "gpt-4o-mini"
                $priThink = Read-YesNo "Enable thinking for Primary?" "Y"
                if ($null -ne $priKey) {
                    Set-EnvValue -FilePath $envFile -Key "PRIMARY_API_KEY" -Value $priKey
                    Write-Success "PRIMARY_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "PRIMARY_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "PRIMARY_API_KEY skipped."
                }
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_BASE_URL" -Value $priBase
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_MODEL" -Value $priModel
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_THINKING_ENABLED" -Value $(if ($priThink -eq "Y") { "true" } else { "false" })

                Write-Host ""
                Write-Host "--- Agentic Brain: Fallback ---" -ForegroundColor Cyan
                if ((Read-YesNo "Fallback = same as Primary?" "N") -eq "Y") {
                    $fblKey = $priKey; $fblBase = $priBase; $fblModel = $priModel; $fblThink = $priThink
                } else {
                    $fblKey = Read-EnvInput "Fallback API Key" "" $true
                    $fblBase = Read-EnvInput "Fallback Base URL" "https://api.openai.com/v1"
                    $fblModel = Read-EnvInput "Fallback Model" "gpt-4o-mini"
                    $fblThink = Read-YesNo "Enable thinking for Fallback?" "Y"
                }
                if ($null -ne $fblKey) {
                    Set-EnvValue -FilePath $envFile -Key "FALLBACK_API_KEY" -Value $fblKey
                    Write-Success "FALLBACK_API_KEY set."
                    $configuredCount++
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "FALLBACK_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "FALLBACK_API_KEY skipped."
                }
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_BASE_URL" -Value $fblBase
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_MODEL" -Value $fblModel
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_THINKING_ENABLED" -Value $(if ($fblThink -eq "Y") { "true" } else { "false" })

                Write-Host ""
                Write-Host "--- Image Generation (optional) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure Image Generation?" "N") -eq "Y") {
                    $imgKey = Read-EnvInput "Image Gen API Key" "" $true
                    $imgEndpoint = Read-EnvInput "Image Gen Endpoint" "https://api.openai.com/v1"
                    $imgModel = Read-EnvInput "Image Gen Model" "dall-e-3"
                    if ($null -ne $imgKey) {
                        Set-EnvValue -FilePath $envFile -Key "IMAGE_GEN_API_KEY" -Value $imgKey
                        Write-Success "IMAGE_GEN_API_KEY set."
                        $configuredCount++
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "IMAGE_GEN_API_KEY" -OnlyIfPlaceholder
                        Write-Warn "IMAGE_GEN_API_KEY skipped."
                    }
                    Set-EnvValue -FilePath $envFile -Key "IMAGE_GEN_ENDPOINT" -Value $imgEndpoint
                    Set-EnvValue -FilePath $envFile -Key "IMAGE_GEN_MODEL" -Value $imgModel
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "IMAGE_GEN_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "Image Generation skipped."
                    $skippedGroups += "Image Gen"
                }

                Write-Host ""
                Write-Host "--- Search & Embeddings (optional) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure Gemini + Tavily?" "N") -eq "Y") {
                    $gem = Read-EnvInput "Gemini API Key" "" $true
                    $tav = Read-EnvInput "Tavily API Key" "" $true
                    if ($null -ne $gem) {
                        Set-EnvValue -FilePath $envFile -Key "GEMINI_API_KEY" -Value $gem
                        Write-Success "GEMINI_API_KEY set."
                        $configuredCount++
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "GEMINI_API_KEY" -OnlyIfPlaceholder
                    }
                    if ($null -ne $tav) {
                        Set-EnvValue -FilePath $envFile -Key "TAVILY_API_KEY" -Value $tav
                        Write-Success "TAVILY_API_KEY set."
                        $configuredCount++
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TAVILY_API_KEY" -OnlyIfPlaceholder
                    }
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "GEMINI_API_KEY" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TAVILY_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "Search/Embeddings skipped."
                    $skippedGroups += "Search"
                }

                Write-Host ""
                Write-Host "--- Voice STT (optional) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure Deepgram (STT)?" "N") -eq "Y") {
                    $dg = Read-EnvInput "Deepgram API Key" "" $true
                    if ($null -ne $dg) {
                        Set-EnvValue -FilePath $envFile -Key "DEEPGRAM_API_KEY" -Value $dg
                        Write-Success "DEEPGRAM_API_KEY set."
                        $configuredCount++
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "DEEPGRAM_API_KEY" -OnlyIfPlaceholder
                        Write-Warn "DEEPGRAM_API_KEY skipped."
                    }
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "DEEPGRAM_API_KEY" -OnlyIfPlaceholder
                    Write-Warn "Deepgram skipped."
                    $skippedGroups += "Deepgram"
                }

                Write-Host ""
                Write-Host "--- Custom TTS (optional; N uses Edge TTS fallback) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure custom TTS?" "N") -eq "Y") {
                    $ttsKey = Read-EnvInput "TTS API Key" "" $true
                    $ttsEndpoint = Read-EnvInput "TTS Endpoint" "" $true
                    if ($null -ne $ttsKey) {
                        Set-EnvValue -FilePath $envFile -Key "TTS_API_KEY" -Value $ttsKey
                        Write-Success "TTS_API_KEY set."
                        $configuredCount++
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TTS_API_KEY" -OnlyIfPlaceholder
                    }
                    if ($null -ne $ttsEndpoint) {
                        Set-EnvValue -FilePath $envFile -Key "TTS_ENDPOINT" -Value $ttsEndpoint
                        Write-Success "TTS_ENDPOINT set."
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TTS_ENDPOINT" -OnlyIfPlaceholder
                    }
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "TTS_API_KEY" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TTS_ENDPOINT" -OnlyIfPlaceholder
                    Write-Warn "Custom TTS skipped (Edge TTS fallback will be used)."
                    $skippedGroups += "TTS"
                }

                Write-Host ""
                Write-Host "--- Telegram (optional) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure Telegram?" "N") -eq "Y") {
                    $tgId = Read-EnvInput "Telegram API ID" "" $true
                    $tgHash = Read-EnvInput "Telegram API Hash" "" $true
                    $tgBot = Read-EnvInput "Telegram Bot Username" "" $true
                    if ($null -ne $tgId) {
                        Set-EnvValue -FilePath $envFile -Key "TELEGRAM_API_ID" -Value $tgId
                        Write-Success "TELEGRAM_API_ID set."
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_ID" -OnlyIfPlaceholder
                    }
                    if ($null -ne $tgHash) {
                        Set-EnvValue -FilePath $envFile -Key "TELEGRAM_API_HASH" -Value $tgHash
                        Write-Success "TELEGRAM_API_HASH set."
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_HASH" -OnlyIfPlaceholder
                    }
                    if ($null -ne $tgBot) {
                        Set-EnvValue -FilePath $envFile -Key "TELEGRAM_BOT_USERNAME" -Value $tgBot
                        Write-Success "TELEGRAM_BOT_USERNAME set."
                    } else {
                        Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_BOT_USERNAME" -OnlyIfPlaceholder
                    }
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_ID" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_HASH" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_BOT_USERNAME" -OnlyIfPlaceholder
                    Write-Warn "Telegram skipped."
                    $skippedGroups += "Telegram"
                }

                $envContent = Get-Content -Path $envFile -Raw -ErrorAction SilentlyContinue
                $priKeyCheck = Get-EnvVal $envContent "PRIMARY_API_KEY"
                $priBaseCheck = Get-EnvVal $envContent "PRIMARY_BASE_URL"
                $fblKeyCheck = Get-EnvVal $envContent "FALLBACK_API_KEY"
                $fblBaseCheck = Get-EnvVal $envContent "FALLBACK_BASE_URL"
                $fbEndCheck = Get-EnvVal $envContent "FAST_BRAIN_ENDPOINT"

                if ($priKeyCheck -like "gsk_*" -and $priBaseCheck -match "openai\.com") {
                    $warnings += "PRIMARY_API_KEY looks like Groq (gsk_) but PRIMARY_BASE_URL is OpenAI — verify!"
                }
                if ($fblKeyCheck -like "gsk_*" -and $fblBaseCheck -match "openai\.com") {
                    $warnings += "FALLBACK_API_KEY looks like Groq (gsk_) but FALLBACK_BASE_URL is OpenAI — verify!"
                }
                if ($fbEndCheck -and $fbEndCheck -notmatch "^https?://") {
                    $warnings += "FAST_BRAIN_ENDPOINT does not look like a URL."
                }

                Write-Host ""
                Write-Host "==========================================================" -ForegroundColor Cyan
                Write-Host "  Configuration Summary" -ForegroundColor Cyan
                Write-Host "==========================================================" -ForegroundColor Cyan
                Write-Host "  Keys configured : $configuredCount" -ForegroundColor Green
                if ($skippedGroups.Count -gt 0) {
                    Write-Host "  Groups skipped  : $($skippedGroups -join ', ')" -ForegroundColor DarkYellow
                } else {
                    Write-Host "  Groups skipped  : none" -ForegroundColor Green
                }
                if ($warnings.Count -gt 0) {
                    Write-Host "  Warnings        :" -ForegroundColor DarkYellow
                    foreach ($w in $warnings) {
                        Write-Host "    - $w" -ForegroundColor DarkYellow
                    }
                }
                Write-Host "  Config file     : $envFile" -ForegroundColor White
                Write-Host "==========================================================" -ForegroundColor Cyan
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