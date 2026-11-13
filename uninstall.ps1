param(
    [string]$InstallPath = ""
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not ("JarvisWin32" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class JarvisWin32 {
    [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr GetStdHandle(int nStdHandle);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
    public static void DisableQuickEdit() {
        IntPtr hIn = GetStdHandle(-10);
        if (hIn != IntPtr.Zero && hIn != new IntPtr(-1)) {
            uint mode;
            if (GetConsoleMode(hIn, out mode)) {
                mode = (mode & ~0x0040u) | 0x0080u;
                SetConsoleMode(hIn, mode);
            }
        }
    }
}
"@ -ErrorAction SilentlyContinue
}

function Disable-ConsoleQuickEdit {
    try {
        [JarvisWin32]::DisableQuickEdit()
    } catch {}
}

Disable-ConsoleQuickEdit

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

function Clear-ConsoleInputBuffer {
    try {
        while ([Console]::KeyAvailable) {
            [void][Console]::ReadKey($true)
        }
    } catch {}
}

function Request-Confirmation {
    param([string]$Prompt, [bool]$DefaultYes = $false)
    if (-not [Environment]::UserInteractive) {
        return $DefaultYes
    }
    Clear-ConsoleInputBuffer
    $suffix = if ($DefaultYes) { "(Y/n)" } else { "(y/N)" }
    $response = Read-Host "  [?] $Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($response)) {
        return $DefaultYes
    }
    return ($response.Trim() -match "^[Yy]")
}

function Broadcast-EnvironmentChange {
    try {
        $result = [UIntPtr]::Zero
        [JarvisWin32]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null
    } catch {}
}

function Get-UserPathRaw {
    try {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Environment", $false)
        if ($null -eq $key) { return "" }
        try {
            return [string]$key.GetValue("Path", "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        } finally { $key.Close() }
    } catch { return "" }
}

function Set-UserPathRaw {
    param([string]$Value)
    try {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Environment", $true)
        if ($null -eq $key) {
            $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey("Environment")
        }
        try {
            $key.SetValue("Path", $Value, [Microsoft.Win32.RegistryValueKind]::ExpandString)
        } finally { $key.Close() }
        return $true
    } catch {
        Write-Fail "Failed to write User PATH to registry: $($_.Exception.Message)"
        return $false
    }
}

function Update-SessionPath {
    param([string]$ExcludeRoot = "")
    try {
        $normalizedExclude = ""
        if (-not [string]::IsNullOrWhiteSpace($ExcludeRoot)) {
            try { $normalizedExclude = [System.IO.Path]::GetFullPath($ExcludeRoot).TrimEnd('\').ToLowerInvariant() } catch {}
        }
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $currentPath = $env:Path
        $combined = @()
        $seen = @{}
        foreach ($source in @($machinePath, $userPath, $currentPath)) {
            if ([string]::IsNullOrWhiteSpace($source)) { continue }
            foreach ($entry in ($source -split ";")) {
                if ([string]::IsNullOrWhiteSpace($entry)) { continue }
                $trimmed = $entry.Trim()
                $expanded = [System.Environment]::ExpandEnvironmentVariables($trimmed).TrimEnd('\').ToLowerInvariant()
                if (-not $expanded) { continue }
                if ($normalizedExclude -and ($expanded -eq $normalizedExclude -or $expanded.StartsWith($normalizedExclude + '\'))) {
                    continue
                }
                if ($expanded -match '\\\.venv\\scripts$' -and $expanded -match 'jarvis') {
                    continue
                }
                if (-not $seen.ContainsKey($expanded)) {
                    $seen[$expanded] = $true
                    $combined += $trimmed
                }
            }
        }
        $env:Path = ($combined -join ";")
    } catch {}
}

function Clear-VenvSessionVars {
    foreach ($v in @("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PYTHONHOME", "PYTHONPATH")) {
        if (Test-Path "Env:\$v") {
            Remove-Item "Env:\$v" -ErrorAction SilentlyContinue
        }
    }
}

function Find-RootFromCandidate {
    param([string]$StartPath)
    if ([string]::IsNullOrWhiteSpace($StartPath)) { return $null }
    $current = $StartPath
    if (Test-Path $current -PathType Leaf) {
        $current = Split-Path -Parent $current
    }
    for ($i = 0; $i -lt 5; $i++) {
        if ([string]::IsNullOrWhiteSpace($current) -or -not (Test-Path $current)) { break }
        if ((Test-Path (Join-Path $current "JarvisProtocol.py")) -or (Test-Path (Join-Path $current "SetupRegistry.py"))) {
            return $current
        }
        $parent = Split-Path -Parent $current
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
    return $null
}

function Find-InstallPathFromRegistry {
    try {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Classes\jarvis\shell\open\command", $false)
        if ($key) {
            try {
                $cmd = [string]$key.GetValue("", $null)
            } finally { $key.Close() }
            if ($cmd) {
                $matchesList = [regex]::Matches($cmd, '"([^"]+)"')
                foreach ($m in $matchesList) {
                    $candidate = $m.Groups[1].Value
                    $root = Find-RootFromCandidate -StartPath $candidate
                    if ($root) { return $root }
                }
            }
        }
    } catch {}
    return $null
}

function Find-InstallPathFromShims {
    try {
        $shims = @(& where.exe jarvis 2>$null)
        foreach ($shim in $shims) {
            if ([string]::IsNullOrWhiteSpace($shim) -or -not (Test-Path $shim)) { continue }
            $root = Find-RootFromCandidate -StartPath $shim
            if ($root) { return $root }
            if ($shim -match '\.(cmd|bat|ps1)$') {
                $raw = Get-Content -Path $shim -Raw -ErrorAction SilentlyContinue
                if ($raw) {
                    $pathMatches = [regex]::Matches($raw, '[A-Za-z]:\\[^"''\r\n]+')
                    foreach ($pm in $pathMatches) {
                        $foundRoot = Find-RootFromCandidate -StartPath $pm.Value
                        if ($foundRoot) { return $foundRoot }
                    }
                }
            }
        }
    } catch {}
    return $null
}

function Find-InstallPathFromCommon {
    $candidates = @(
        (Join-Path $HOME "Jarvis-OS-Agent"),
        (Join-Path $HOME "jarvis-os-agent"),
        (Join-Path $HOME "Jarvis"),
        (Join-Path $HOME "jarvis"),
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "Jarvis-OS-Agent"),
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "jarvis-os-agent")
    )
    foreach ($c in $candidates) {
        if ($c -and ((Test-Path (Join-Path $c "JarvisProtocol.py")) -or (Test-Path (Join-Path $c "SetupRegistry.py")))) {
            return $c
        }
    }
    return $null
}

function Resolve-InstallPath {
    param([string]$OverridePath)
    if ($OverridePath -and (Test-Path $OverridePath)) {
        try { return (Resolve-Path $OverridePath).Path } catch { return $OverridePath }
    }
    $p = Find-InstallPathFromRegistry
    if ($p) { return $p }
    $p = Find-InstallPathFromShims
    if ($p) { return $p }
    $p = Find-InstallPathFromCommon
    if ($p) { return $p }
    return $null
}

function Get-AncestorPids {
    $ancestors = @{}
    $parentMap = @{}
    try {
        foreach ($p in (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
            $parentMap[[int]$p.ProcessId] = [int]$p.ParentProcessId
        }
        $curr = [int]$PID
        for ($i = 0; $i -lt 16; $i++) {
            if (-not $curr -or $ancestors.ContainsKey($curr)) { break }
            $ancestors[$curr] = $true
            if ($parentMap.ContainsKey($curr)) {
                $curr = $parentMap[$curr]
            } else {
                break
            }
        }
    } catch {
        $ancestors[[int]$PID] = $true
    }
    return $ancestors
}

function Stop-JarvisProcesses {
    param([string]$TargetDir)
    $normalizedTarget = ""
    $targetWithSlash = ""
    if ($TargetDir -and (Test-Path $TargetDir)) {
        try {
            $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\').ToLowerInvariant()
            $targetWithSlash = $normalizedTarget + '\'
        } catch {}
    }

    $ancestorPids = Get-AncestorPids
    $allowedNames = @("python.exe", "pythonw.exe", "node.exe", "jarvis.exe", "pip.exe")
    $killedCount = 0

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if ($ancestorPids.ContainsKey([int]$_.ProcessId)) { return $false }
        $procName = if ($_.Name) { $_.Name.ToLowerInvariant() } else { "" }
        $exePath = if ($_.ExecutablePath) { $_.ExecutablePath.ToLowerInvariant() } else { "" }
        $cmdLine = if ($_.CommandLine) { $_.CommandLine.ToLowerInvariant() } else { "" }

        if ($targetWithSlash -and $exePath.StartsWith($targetWithSlash)) {
            return $true
        }
        if ($allowedNames -contains $procName) {
            if ($targetWithSlash -and $cmdLine.Contains($targetWithSlash)) {
                return $true
            }
            if ($cmdLine.Contains("jarvisprotocol.py") -or $cmdLine.Contains("baileysserver")) {
                return $true
            }
        }
        return $false
    }

    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            $killedCount++
        } catch {}
    }

    if ($TargetDir -and (Test-Path $TargetDir)) {
        foreach ($lf in @(".jarvis.lock", "jarvis.lock", ".jarvis_update.lock")) {
            $lockFile = Join-Path $TargetDir $lf
            if (Test-Path $lockFile) {
                Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
            }
        }
    }

    if ($killedCount -gt 0) {
        Start-Sleep -Seconds 2
        Write-Success "Terminated $killedCount running J.A.R.V.I.S. process(es)."
    } else {
        Write-Success "No active J.A.R.V.I.S. processes found."
    }
}

function Backup-UserData {
    param([string]$InstallPath)
    if (-not $InstallPath -or -not (Test-Path $InstallPath)) { return $true }

    $envFile = Join-Path $InstallPath ".env"
    $memoryDir = Join-Path $InstallPath "Data\jarvis_memory"
    $indexerDir = Join-Path $InstallPath "Data\jarvis_indexer"
    $mcpFile = Join-Path $InstallPath "Data\mcp_servers.json"
    $cookiesDir = Join-Path $InstallPath "Data\SessionCookies"

    $hasUserData = (Test-Path $envFile) -or (Test-Path $memoryDir) -or (Test-Path $indexerDir) -or (Test-Path $mcpFile) -or (Test-Path $cookiesDir)
    if (-not $hasUserData) {
        Write-Success "No custom user configuration found to back up."
        return $true
    }

    if (-not (Request-Confirmation -Prompt "Backup .env, memory graph, MCP config, and saved sessions to Desktop?" -DefaultYes $true)) {
        Write-Warn "Skipping backup. All keys, sessions, and memories will be permanently destroyed."
        return $true
    }

    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktopDir) -or -not (Test-Path $desktopDir)) {
        $desktopDir = $HOME
    }
    $backupFolder = Join-Path $desktopDir "Jarvis_Backup_$timestamp"

    try {
        New-Item -ItemType Directory -Path $backupFolder -Force -ErrorAction Stop | Out-Null
        if (Test-Path $envFile) { Copy-Item -Path $envFile -Destination (Join-Path $backupFolder ".env") -Force -ErrorAction Stop }
        if (Test-Path $mcpFile) { Copy-Item -Path $mcpFile -Destination (Join-Path $backupFolder "mcp_servers.json") -Force -ErrorAction Stop }
        if (Test-Path $memoryDir) { Copy-Item -Path $memoryDir -Destination (Join-Path $backupFolder "jarvis_memory") -Recurse -Force -ErrorAction Stop }
        if (Test-Path $indexerDir) { Copy-Item -Path $indexerDir -Destination (Join-Path $backupFolder "jarvis_indexer") -Recurse -Force -ErrorAction Stop }
        if (Test-Path $cookiesDir) { Copy-Item -Path $cookiesDir -Destination (Join-Path $backupFolder "SessionCookies") -Recurse -Force -ErrorAction Stop }
        Write-Success "Backup saved to: $backupFolder"
        return $true
    } catch {
        Write-Fail "Backup failed: $($_.Exception.Message)"
        if (-not (Request-Confirmation -Prompt "Backup failed. Continue with uninstall anyway?" -DefaultYes $false)) {
            return $false
        }
        return $true
    }
}

function Uninstall-CliPackage {
    param([string]$TargetDir)
    if (-not $TargetDir -or -not (Test-Path $TargetDir)) {
        Write-Success "No virtual environment present; skipping pip uninstall."
        return
    }
    $venvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        try {
            & $venvPython -m pip uninstall jarvis-cli -y 2>&1 | Out-Null
            Write-Success "Uninstalled 'jarvis-cli' package from virtual environment."
        } catch {
            Write-Warn "pip uninstall reported an issue (package may already be removed)."
        }
    } else {
        Write-Success "No virtual environment Python found; skipping pip uninstall."
    }
}

function Remove-GlobalCliRegistration {
    param([string]$TargetDir)

    $shimLocations = @(
        "$env:USERPROFILE\.local\bin\jarvis.cmd",
        "$env:USERPROFILE\.local\bin\jarvis.exe",
        "$env:USERPROFILE\.local\bin\jarvis.bat",
        "$env:USERPROFILE\.local\bin\jarvis.ps1",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\jarvis.cmd",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\jarvis.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\jarvis.bat",
        "$env:LOCALAPPDATA\Programs\Python\Launcher\jarvis.cmd",
        "$env:LOCALAPPDATA\Programs\Python\Launcher\jarvis.exe",
        "$HOME\jarvis.cmd",
        "$HOME\jarvis.bat",
        "$HOME\jarvis.exe",
        "$HOME\jarvis.ps1"
    )

    $pyScriptRoots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:APPDATA\Python",
        "$env:ProgramFiles"
    )
    foreach ($pyRoot in $pyScriptRoots) {
        if ($pyRoot -and (Test-Path $pyRoot)) {
            $pyDirs = Get-ChildItem -Path $pyRoot -Filter "Python*" -Directory -ErrorAction SilentlyContinue
            foreach ($pd in $pyDirs) {
                $scriptsDir = Join-Path $pd.FullName "Scripts"
                if (Test-Path $scriptsDir) {
                    foreach ($ext in @("jarvis.exe", "jarvis.cmd", "jarvis.bat", "jarvis-script.py", "jarvis.ps1")) {
                        $shimLocations += (Join-Path $scriptsDir $ext)
                    }
                }
            }
        }
    }

    if ($TargetDir) {
        $shimLocations += @(
            (Join-Path $TargetDir ".venv\Scripts\jarvis.exe"),
            (Join-Path $TargetDir ".venv\Scripts\jarvis-script.py"),
            (Join-Path $TargetDir ".venv\Scripts\jarvis.cmd"),
            (Join-Path $TargetDir ".venv\Scripts\jarvis.bat"),
            (Join-Path $TargetDir ".venv\Scripts\jarvis.ps1")
        )
    }

    try {
        $resolvedShims = @(& where.exe jarvis 2>$null)
        foreach ($rs in $resolvedShims) {
            if (-not [string]::IsNullOrWhiteSpace($rs) -and (Test-Path $rs)) {
                $shimLocations += $rs.Trim()
            }
        }
    } catch {}

    $removedShims = 0
    $uniqueShims = $shimLocations | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    foreach ($shim in $uniqueShims) {
        if (Test-Path $shim) {
            Remove-Item -Path $shim -Force -ErrorAction SilentlyContinue
            if (-not (Test-Path $shim)) {
                Write-Success "Removed CLI shim: $shim"
                $removedShims++
            }
        }
    }
    if ($removedShims -eq 0) {
        Write-Success "No global CLI shims found to remove."
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
            if (-not (Test-Path $reg)) {
                Write-Success "Cleaned registry key: $reg"
            } else {
                Write-Fail "Could not remove registry key: $reg"
            }
        }
    }
}

function Remove-PathEntries {
    param([string]$TargetDir)

    $rawPath = Get-UserPathRaw
    if ([string]::IsNullOrWhiteSpace($rawPath)) {
        Update-SessionPath -ExcludeRoot $TargetDir
        Write-Success "User PATH is empty; nothing to clean."
        return
    }

    $normalizedTarget = ""
    if ($TargetDir) {
        try { $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\').ToLowerInvariant() } catch {}
    }

    $parts = $rawPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $filtered = @()
    $removedCount = 0

    foreach ($part in $parts) {
        $trimmed = $part.Trim().TrimEnd('\')
        $expanded = [System.Environment]::ExpandEnvironmentVariables($trimmed).TrimEnd('\').ToLowerInvariant()
        $shouldRemove = $false

        if ($normalizedTarget) {
            if ($expanded -eq $normalizedTarget -or $expanded.StartsWith($normalizedTarget + '\')) {
                $shouldRemove = $true
            }
        }

        if (-not $shouldRemove -and $expanded -match '\\\.venv\\scripts$' -and $expanded -match 'jarvis') {
            $shouldRemove = $true
        }

        if (-not $shouldRemove -and $expanded -match '\\\.venv\\scripts$') {
            $grandParent = $expanded.Substring(0, $expanded.Length - '\scripts'.Length)
            $grandParent = $grandParent.Substring(0, $grandParent.Length - '\.venv'.Length)
            if ($grandParent -and (Test-Path (Join-Path $grandParent "JarvisProtocol.py") -ErrorAction SilentlyContinue)) {
                $shouldRemove = $true
            }
        }

        if ($shouldRemove) {
            $removedCount++
        } else {
            $filtered += $part
        }
    }

    if ($removedCount -gt 0) {
        $newPath = $filtered -join ";"
        if (Set-UserPathRaw -Value $newPath) {
            Write-Success "Removed $removedCount J.A.R.V.I.S. entry/entries from User PATH."
        }
    } else {
        Write-Success "No J.A.R.V.I.S. entries found in User PATH."
    }

    Update-SessionPath -ExcludeRoot $TargetDir
    Broadcast-EnvironmentChange
}

$script:DeferredCleanupScheduled = $false

function Remove-DirectoryTreeForce {
    param([string]$PathToRemove, [switch]$AllowDeferred)
    if ([string]::IsNullOrWhiteSpace($PathToRemove) -or -not (Test-Path $PathToRemove)) {
        return $true
    }

    $fullPath = $PathToRemove
    try { $fullPath = [System.IO.Path]::GetFullPath($PathToRemove) } catch {}

    & cmd.exe /c "rmdir /s /q `"$fullPath`"" 2>$null

    if (Test-Path $fullPath) {
        Get-ChildItem -LiteralPath $fullPath -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                if ($_.Attributes -band [System.IO.FileAttributes]::ReadOnly) {
                    $_.Attributes = $_.Attributes -bxor [System.IO.FileAttributes]::ReadOnly
                }
            } catch {}
        }
        Remove-Item -LiteralPath $fullPath -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path $fullPath) {
        Start-Sleep -Milliseconds 750
        & cmd.exe /c "rmdir /s /q `"\\?\$fullPath`"" 2>$null
        if (Test-Path $fullPath) {
            Remove-Item -LiteralPath $fullPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    if ((Test-Path $fullPath) -and $AllowDeferred) {
        try {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c ping 127.0.0.1 -n 3 >nul & rmdir /s /q `"$fullPath`" 2>nul & rmdir /s /q `"\\?\$fullPath`" 2>nul" -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
            $script:DeferredCleanupScheduled = $true
            return $true
        } catch {}
    }

    return (-not (Test-Path $fullPath))
}

function Test-UninstallComplete {
    param([string]$InstallPath)
    $issues = @()

    if (Test-Path "HKCU:\Software\Classes\jarvis") {
        $issues += "URL protocol 'jarvis://' is still registered in the registry."
    }

    if ($InstallPath -and (Test-Path $InstallPath) -and -not $script:DeferredCleanupScheduled) {
        $issues += "Install directory still exists: $InstallPath"
    }

    try {
        $found = @(& where.exe jarvis 2>$null)
        if ($found.Count -gt 0) {
            $issues += "Command 'jarvis' is still resolvable: $($found -join ', ')"
        }
    } catch {}

    $userPath = Get-UserPathRaw
    if ($userPath -and $InstallPath) {
        $n = ""
        try { $n = [System.IO.Path]::GetFullPath($InstallPath).TrimEnd('\').ToLowerInvariant() } catch {}
        if ($n) {
            foreach ($p in ($userPath -split ";" | Where-Object { $_ })) {
                $e = [System.Environment]::ExpandEnvironmentVariables($p).TrimEnd('\').ToLowerInvariant()
                if ($e -eq $n -or $e.StartsWith($n + '\')) {
                    $issues += "User PATH still contains entry: $p"
                    break
                }
            }
        }
    }

    return $issues
}

function Uninstall-Jarvis {
    param([string]$InstallPathOverride)

    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "   J.A.R.V.I.S. OS Agent - Complete System Uninstaller    " -ForegroundColor Red
    Write-Host "==========================================================" -ForegroundColor Red

    Clear-VenvSessionVars

    $installPath = Resolve-InstallPath -OverridePath $InstallPathOverride
    $docsJarvisPath = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Jarvis"
    $hfModelCache = Join-Path $HOME ".cache\huggingface\hub\models--BAAI--bge-small-en-v1.5"

    if (-not $installPath) {
        Write-Warn "Could not auto-detect J.A.R.V.I.S. installation directory."
        if (-not (Request-Confirmation -Prompt "Continue with deep cleanup (registry, PATH, shims, caches only)?" -DefaultYes $false)) {
            Write-Host ""
            Write-Host "Uninstallation cancelled." -ForegroundColor Cyan
            return
        }
    } else {
        Write-Host ""
        Write-Host "  Detected Install Path : $installPath" -ForegroundColor White
        Write-Host ""
        if (-not (Request-Confirmation -Prompt "Are you sure you want to uninstall J.A.R.V.I.S. OS Agent?" -DefaultYes $false)) {
            Write-Host ""
            Write-Host "Uninstallation aborted by user." -ForegroundColor Cyan
            return
        }
    }

    Set-Location -Path $HOME

    Write-Step "1/7" "Stopping Active J.A.R.V.I.S. Processes & Servers..."
    Stop-JarvisProcesses -TargetDir $installPath

    Write-Step "2/7" "Backing Up User Configuration, Memory & Credentials..."
    if ($installPath) {
        if (-not (Backup-UserData -InstallPath $installPath)) {
            Write-Host ""
            Write-Host "Uninstallation aborted (backup declined after failure)." -ForegroundColor Cyan
            return
        }
    } else {
        Write-Success "No install directory detected; skipping backup."
    }

    Write-Step "3/7" "Unregistering 'jarvis' CLI Package from Virtual Environment..."
    Uninstall-CliPackage -TargetDir $installPath

    Write-Step "4/7" "Removing CLI Shims, Registry Keys & PATH Entries..."
    Remove-GlobalCliRegistration -TargetDir $installPath
    Remove-PathEntries -TargetDir $installPath

    Write-Step "5/7" "Removing J.A.R.V.I.S. Core Directory (.venv, codebase)..."
    if ($installPath -and (Test-Path $installPath)) {
        $setupFile = Join-Path $installPath "setup.py"
        if (Test-Path $setupFile) { Remove-Item -Path $setupFile -Force -ErrorAction SilentlyContinue }
        Get-ChildItem -Path $installPath -Filter "*.egg-info" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        Get-ChildItem -Path $installPath -Filter "*.egg-link" -File -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
        }
        Write-Host "  -> Deleting $installPath ..." -ForegroundColor DarkGray
        if (Remove-DirectoryTreeForce -PathToRemove $installPath -AllowDeferred) {
            Write-Success "Removed $installPath completely."
        } else {
            Write-Fail "Could not delete all files in $installPath. Close all terminals/editors and remove manually."
        }
    } else {
        Write-Success "Core directory already absent."
    }

    $localAppDataJarvis = Join-Path $env:LOCALAPPDATA "Jarvis"
    if (Test-Path $localAppDataJarvis) {
        [void](Remove-DirectoryTreeForce -PathToRemove $localAppDataJarvis)
    }

    Write-Step "6/7" "Checking External MediaVault & Shared Files..."
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

    Write-Step "7/7" "Checking Cached Local Embedding Models..."
    if (Test-Path $hfModelCache) {
        if (Request-Confirmation -Prompt "Remove cached BAAI/bge-small-en-v1.5 embedding model (~130 MB)?" -DefaultYes $false) {
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

    Broadcast-EnvironmentChange
    Update-SessionPath -ExcludeRoot $installPath

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "   Running Post-Uninstall Verification..." -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    $issues = Test-UninstallComplete -InstallPath $installPath
    if ($issues.Count -eq 0) {
        Write-Success "All clear. No residual J.A.R.V.I.S. artifacts detected."
    } else {
        foreach ($i in $issues) { Write-Warn $i }
        Write-Host ""
        Write-Host "  Some residual items detected. See warnings above." -ForegroundColor DarkYellow
        Write-Host "  If PATH entries remain, open a NEW terminal and re-run this script." -ForegroundColor DarkYellow
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "     J.A.R.V.I.S. OS Agent Uninstalled Successfully!      " -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Please open a NEW terminal window to apply PATH changes." -ForegroundColor Cyan
    Write-Host ""
}

Uninstall-Jarvis -InstallPathOverride $InstallPath