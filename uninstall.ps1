$ErrorActionPreference = "Continue"
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

function Request-Confirmation {
    param([string]$Prompt, [bool]$DefaultYes = $false)
    if (-not [Environment]::UserInteractive) {
        return $DefaultYes
    }
    $suffix = if ($DefaultYes) { "(Y/n)" } else { "(y/N)" }
    $response = Read-Host "  [?] $Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($response)) {
        return $DefaultYes
    }
    return ($response -match "^[Yy]")
}

function Update-SessionPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Stop-JarvisProcesses {
    param([string]$TargetDir)
    $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).ToLowerInvariant()
    $killedCount = 0

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant().StartsWith($normalizedTarget)) -or
        ($_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($normalizedTarget))
    }

    foreach ($proc in $processes) {
        if ($proc.ProcessId -ne $PID) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
                $killedCount++
            } catch {}
        }
    }

    $lockFile = Join-Path $TargetDir "jarvis.lock"
    if (Test-Path $lockFile) {
        Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
    }

    if ($killedCount -gt 0) {
        Start-Sleep -Seconds 2
        Write-Success "Terminated $killedCount running J.A.R.V.I.S. background process(es)."
    } else {
        Write-Success "No active J.A.R.V.I.S. background processes found."
    }
}

function Remove-GlobalCliRegistration {
    param([string]$TargetDir)
    $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\').ToLowerInvariant()

    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath) {
        $pathParts = $userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        $filteredParts = @()
        $removedAny = $false

        foreach ($part in $pathParts) {
            $cleanPart = $part.Trim().TrimEnd('\').ToLowerInvariant()
            if ($cleanPart.StartsWith($normalizedTarget) -or $cleanPart -like "*jarvis-os-agent*") {
                $removedAny = $true
            } else {
                $filteredParts += $part
            }
        }

        if ($removedAny) {
            $newPath = $filteredParts -join ";"
            [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            Write-Success "Removed J.A.R.V.I.S. entries from User PATH."
        }
    }

    $shimLocations = @(
        "$env:USERPROFILE\.local\bin\jarvis.cmd",
        "$env:USERPROFILE\.local\bin\jarvis.bat",
        "$env:USERPROFILE\.local\bin\jarvis.ps1",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\jarvis.cmd",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\jarvis.bat",
        "$env:LOCALAPPDATA\Programs\Python\Launcher\jarvis.cmd",
        "$HOME\jarvis.cmd",
        "$HOME\jarvis.bat"
    )

    foreach ($shim in $shimLocations) {
        if (Test-Path $shim) {
            Remove-Item -Path $shim -Force -ErrorAction SilentlyContinue
            Write-Success "Removed CLI shim: $shim"
        }
    }

    $regPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\jarvis.exe",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\jarvis.bat",
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\jarvis.cmd",
        "HKCU:\Software\Classes\jarvis"
    )

    foreach ($reg in $regPaths) {
        if (Test-Path $reg) {
            Remove-Item -Path $reg -Recurse -Force -ErrorAction SilentlyContinue
            Write-Success "Cleaned registry key: $reg"
        }
    }

    Update-SessionPath
}

function Remove-DirectoryTreeForce {
    param([string]$PathToRemove)
    if (-not (Test-Path $PathToRemove)) {
        return $true
    }

    Get-ChildItem -Path $PathToRemove -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            if ($_.Attributes -band [System.IO.FileAttributes]::ReadOnly) {
                $_.Attributes = $_.Attributes -bxor [System.IO.FileAttributes]::ReadOnly
            }
        } catch {}
    }

    Remove-Item -Path $PathToRemove -Recurse -Force -ErrorAction SilentlyContinue

    if (Test-Path $PathToRemove) {
        & cmd.exe /c "rmdir /s /q `"$PathToRemove`"" 2>$null
    }

    return (-not (Test-Path $PathToRemove))
}

function Uninstall-Jarvis {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "   J.A.R.V.I.S. OS Agent - Complete System Uninstaller    " -ForegroundColor Red
    Write-Host "==========================================================" -ForegroundColor Red

    $installPath = Join-Path $HOME "Jarvis-OS-Agent"
    $docsJarvisPath = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Jarvis"
    $hfModelCache = Join-Path $HOME ".cache\huggingface\hub\models--BAAI--bge-small-en-v1.5"

    if (-not (Test-Path $installPath)) {
        Write-Warn "Main installation folder not found at $installPath."
        if (-not (Request-Confirmation -Prompt "Do you still want to run deep cleanup for registry, PATH, and cached data?" -DefaultYes $false)) {
            Write-Host ""
            Write-Host "Uninstallation cancelled." -ForegroundColor Cyan
            return
        }
    } else {
        Write-Host ""
        Write-Host "  Target Installation : $installPath" -ForegroundColor White
        if (-not (Request-Confirmation -Prompt "Are you sure you want to uninstall J.A.R.V.I.S. OS Agent?" -DefaultYes $false)) {
            Write-Host ""
            Write-Host "Uninstallation aborted by user." -ForegroundColor Cyan
            return
        }
    }

    Set-Location -Path $HOME

    Write-Step "1/6" "Stopping Active J.A.R.V.I.S. Processes & Servers..."
    Stop-JarvisProcesses -TargetDir $installPath

    Write-Step "2/6" "Checking User Configuration, Memory & Credentials..."
    if (Test-Path $installPath) {
        $envFile = Join-Path $installPath ".env"
        $memoryDir = Join-Path $installPath "Data\jarvis_memory"
        $indexerDir = Join-Path $installPath "Data\jarvis_indexer"
        $mcpFile = Join-Path $installPath "Data\mcp_servers.json"

        $hasUserData = (Test-Path $envFile) -or (Test-Path $memoryDir) -or (Test-Path $mcpFile)
        if ($hasUserData) {
            if (Request-Confirmation -Prompt "Backup your .env API keys, Lifelong Memory Graph, and MCP config to Desktop before deleting?" -DefaultYes $true) {
                $desktopDir = [Environment]::GetFolderPath("Desktop")
                $backupFolder = Join-Path $desktopDir "Jarvis_Backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
                New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null

                if (Test-Path $envFile) {
                    Copy-Item -Path $envFile -Destination (Join-Path $backupFolder ".env") -Force
                }
                if (Test-Path $mcpFile) {
                    Copy-Item -Path $mcpFile -Destination (Join-Path $backupFolder "mcp_servers.json") -Force
                }
                if (Test-Path $memoryDir) {
                    Copy-Item -Path $memoryDir -Destination (Join-Path $backupFolder "jarvis_memory") -Recurse -Force
                }
                if (Test-Path $indexerDir) {
                    Copy-Item -Path $indexerDir -Destination (Join-Path $backupFolder "jarvis_indexer") -Recurse -Force
                }
                Write-Success "Backup saved to: $backupFolder"
            } else {
                Write-Warn "Skipping backup. All keys, sessions, and memories inside $installPath will be permanently destroyed."
            }
        } else {
            Write-Success "No custom user configuration found to back up."
        }
    }

    Write-Step "3/6" "Unregistering Global 'jarvis' Command & Cleaning Registry..."
    Remove-GlobalCliRegistration -TargetDir $installPath
    Write-Success "Global CLI registration and PATH variables cleaned."

    Write-Step "4/6" "Removing J.A.R.V.I.S. Core Directory (.venv, node_modules, codebase)..."
    if (Test-Path $installPath) {
        Write-Host "  -> Deleting $installPath (this may take a moment)..." -ForegroundColor DarkGray
        if (Remove-DirectoryTreeForce -PathToRemove $installPath) {
            Write-Success "Removed $installPath completely."
        } else {
            Write-Fail "Could not delete some locked files in $installPath. Close all terminals and delete the folder manually."
        }
    } else {
        Write-Success "Core directory already absent."
    }

    Write-Step "5/6" "Checking External MediaVault & Shared Files..."
    if (Test-Path $docsJarvisPath) {
        Write-Warn "Found external Jarvis media/files folder at: $docsJarvisPath"
        if (Request-Confirmation -Prompt "Permanently delete downloaded WhatsApp media and shared files in '$docsJarvisPath'?" -DefaultYes $false) {
            if (Remove-DirectoryTreeForce -PathToRemove $docsJarvisPath) {
                Write-Success "Deleted $docsJarvisPath"
            } else {
                Write-Fail "Failed to remove $docsJarvisPath"
            }
        } else {
            Write-Success "Preserved $docsJarvisPath"
        }
    } else {
        Write-Success "No external Documents\Jarvis directory found."
    }

    Write-Step "6/6" "Checking Cached Local Embedding Models..."
    if (Test-Path $hfModelCache) {
        if (Request-Confirmation -Prompt "Remove cached BAAI/bge-small-en-v1.5 embedding model (~130 MB) from HuggingFace cache?" -DefaultYes $false) {
            if (Remove-DirectoryTreeForce -PathToRemove $hfModelCache) {
                Write-Success "Removed cached embedding model."
            } else {
                Write-Warn "Could not remove HuggingFace cache directory."
            }
        } else {
            Write-Success "Preserved HuggingFace model cache."
        }
    } else {
        Write-Success "No residual embedding cache found."
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "     J.A.R.V.I.S. OS Agent Uninstalled Successfully!      " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host ""
}

Uninstall-Jarvis