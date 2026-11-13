param(
    [string]$InstallPath = "",
    [ValidateSet("", "stable", "edge", "pinned")]
    [string]$Channel = "",
    [switch]$Check,
    [switch]$Silent,
    [switch]$AutoUpdate,
    [switch]$Rollback,
    [switch]$Force,
    [int]$EdgePromptCooldownDays = 7
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$script:ExitCode = 0

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
    try { [JarvisWin32]::DisableQuickEdit() } catch {}
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

function Write-Info {
    param([string]$Message)
    Write-Host "  [i] $Message" -ForegroundColor Cyan
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
    if (-not [Environment]::UserInteractive) { return $DefaultYes }
    Clear-ConsoleInputBuffer
    $suffix = if ($DefaultYes) { "(Y/n)" } else { "(y/N)" }
    $response = Read-Host "  [?] $Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($response)) { return $DefaultYes }
    return ($response.Trim() -match "^[Yy]")
}

function Read-YesNo {
    param([string]$Question, [string]$Default = "N")
    if (-not [Environment]::UserInteractive) { return $Default }
    $hint = if ($Default -eq "Y") { "(Y/n)" } else { "(y/N)" }
    Clear-ConsoleInputBuffer
    while ($true) {
        $ans = Read-Host "  $Question $hint"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
        $ans = $ans.Trim().ToLowerInvariant()
        if ($ans -eq "y" -or $ans -eq "yes") { return "Y" }
        if ($ans -eq "n" -or $ans -eq "no") { return "N" }
        Write-Host "    [!] Please answer y or n." -ForegroundColor DarkYellow
    }
}

function Broadcast-EnvironmentChange {
    try {
        $result = [UIntPtr]::Zero
        [JarvisWin32]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null
    } catch {}
}

function Update-SessionPath {
    try {
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
                if ($expanded -and -not $seen.ContainsKey($expanded)) {
                    $seen[$expanded] = $true
                    $combined += $trimmed
                }
            }
        }
        $env:Path = ($combined -join ";")
    } catch {}
}

function Find-RootFromCandidate {
    param([string]$StartPath)
    if ([string]::IsNullOrWhiteSpace($StartPath)) { return $null }
    $current = $StartPath
    if (Test-Path $current -PathType Leaf) { $current = Split-Path -Parent $current }
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
            try { $cmd = [string]$key.GetValue("", $null) } finally { $key.Close() }
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
    $allowedNames = @("python.exe", "pythonw.exe", "node.exe", "jarvis.exe", "pip.exe")
    $killedCount = 0
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if ($_.ProcessId -eq $PID) { return $false }
        $procName = if ($_.Name) { $_.Name.ToLowerInvariant() } else { "" }
        $exePath = if ($_.ExecutablePath) { $_.ExecutablePath.ToLowerInvariant() } else { "" }
        $cmdLine = if ($_.CommandLine) { $_.CommandLine.ToLowerInvariant() } else { "" }
        if ($targetWithSlash -and $exePath.StartsWith($targetWithSlash)) { return $true }
        if ($allowedNames -contains $procName) {
            if ($targetWithSlash -and $cmdLine.Contains($targetWithSlash)) { return $true }
            if ($cmdLine.Contains("jarvisprotocol.py") -or $cmdLine.Contains("baileysserver")) { return $true }
        }
        return $false
    }
    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            $killedCount++
        } catch {}
    }
    if ($killedCount -gt 0) {
        Start-Sleep -Seconds 2
        Write-Success "Terminated $killedCount running J.A.R.V.I.S. process(es)."
    } else {
        Write-Success "No active J.A.R.V.I.S. processes found."
    }
}

function Get-NpmExecutable {
    $npmCmd = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue
    if ($npmCmd) { return $npmCmd.Source }
    $fallbacks = @(
        "$env:LOCALAPPDATA\Programs\nodejs\npm.cmd",
        "$env:ProgramFiles\nodejs\npm.cmd"
    )
    foreach ($fb in $fallbacks) {
        if (Test-Path $fb) { return $fb }
    }
    $npmAny = Get-Command npm -ErrorAction SilentlyContinue
    if ($npmAny) { return $npmAny.Source }
    return $null
}

function Acquire-UpdateLock {
    param([string]$TargetDir)
    $lockPath = Join-Path $TargetDir ".jarvis_update.lock"
    if (Test-Path $lockPath) {
        try {
            $content = Get-Content -Path $lockPath -Raw -ErrorAction SilentlyContinue
            $data = $null
            try { $data = $content | ConvertFrom-Json -ErrorAction SilentlyContinue } catch {}
            if ($data -and $data.Pid) {
                $proc = Get-Process -Id $data.Pid -ErrorAction SilentlyContinue
                if ($proc -and $proc.ProcessName -match "powershell|pwsh") {
                    return @{ Acquired = $false; Reason = "Another update is already running (PID $($data.Pid))." }
                }
            }
        } catch {}
        Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
    }
    $lockData = @{
        Pid       = $PID
        StartedAt = (Get-Date).ToUniversalTime().ToString("o")
        User      = $env:USERNAME
        Machine   = $env:COMPUTERNAME
    }
    try {
        $json = $lockData | ConvertTo-Json
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($lockPath, $json, $utf8)
        return @{ Acquired = $true; Path = $lockPath }
    } catch {
        return @{ Acquired = $false; Reason = "Failed to create lock file: $($_.Exception.Message)" }
    }
}

function Release-UpdateLock {
    param([string]$LockPath)
    if ($LockPath -and (Test-Path $LockPath)) {
        Remove-Item -Path $LockPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-StatePath {
    param([string]$TargetDir)
    return Join-Path $TargetDir ".jarvis_state.json"
}

function Read-StateFile {
    param([string]$TargetDir)
    $path = Get-StatePath -TargetDir $TargetDir
    if (-not (Test-Path $path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch { return $null }
}

function Write-StateFile {
    param([string]$TargetDir, $State)
    $path = Get-StatePath -TargetDir $TargetDir
    try {
        $json = $State | ConvertTo-Json -Depth 10
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($path, $json, $utf8)
        return $true
    } catch { return $false }
}

function New-DefaultState {
    return [pscustomobject]@{
        channel                      = "stable"
        version                      = ""
        commit                       = ""
        deps_hash                    = ""
        npm_hash                     = ""
        last_edge_prompt_at          = $null
        edge_prompt_dismissed_count  = 0
        edge_prompt_permanently_muted = $false
        last_rollback_at             = $null
        last_updated_at              = $null
    }
}

function Invoke-GitCommand {
    param([string]$WorkingDir, [string[]]$Arguments)
    if (-not (Test-Path $WorkingDir)) {
        return @{ ExitCode = -1; Output = @("Working directory not found: $WorkingDir") }
    }
    Push-Location $WorkingDir
    try {
        $output = & git @Arguments 2>&1
        return @{ ExitCode = $LASTEXITCODE; Output = $output }
    } catch {
        return @{ ExitCode = -1; Output = @("$($_.Exception.Message)") }
    } finally {
        Pop-Location
    }
}

function Get-CurrentCommit {
    param([string]$TargetDir)
    $r = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("rev-parse", "HEAD")
    if ($r.ExitCode -eq 0) { return "$($r.Output)".Trim() }
    return ""
}

function Get-CurrentTag {
    param([string]$TargetDir)
    $r = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("describe", "--tags", "--exact-match", "HEAD")
    if ($r.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace("$($r.Output)")) {
        return "$($r.Output)".Trim()
    }
    return $null
}

function Get-LatestStableTag {
    param([string]$TargetDir)
    $r = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("describe", "--tags", "--abbrev=0", "--match", "v*", "--exclude", "*-*")
    if ($r.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace("$($r.Output)")) {
        return "$($r.Output)".Trim()
    }
    $r2 = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("describe", "--tags", "--abbrev=0")
    if ($r2.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace("$($r2.Output)")) {
        return "$($r2.Output)".Trim()
    }
    return $null
}

function Get-EdgeInfo {
    param([string]$TargetDir)
    $localHead = Get-CurrentCommit -TargetDir $TargetDir
    $remoteR = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("rev-parse", "origin/main")
    if ($remoteR.ExitCode -ne 0) { return $null }
    $remoteCommit = "$($remoteR.Output)".Trim()
    if ($remoteCommit -eq $localHead) {
        return @{ AheadCount = 0; Commits = @(); LatestMessage = ""; RemoteCommit = $remoteCommit }
    }
    $countR = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("rev-list", "--count", "HEAD..origin/main")
    $aheadCount = 0
    if ($countR.ExitCode -eq 0) {
        try { $aheadCount = [int]"$($countR.Output)".Trim() } catch {}
    }
    $logR = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("log", "HEAD..origin/main", "--oneline", "--no-merges", "-n", "20")
    $commits = @()
    if ($logR.ExitCode -eq 0) {
        $commits = @($logR.Output | Where-Object { -not [string]::IsNullOrWhiteSpace("$_") })
    }
    $latestMsg = ""
    if ($commits.Count -gt 0) {
        $latestMsg = "$($commits[0])" -replace '^[a-f0-9]+\s+', ''
    }
    return @{
        AheadCount    = $aheadCount
        Commits       = $commits
        LatestMessage = $latestMsg
        RemoteCommit  = $remoteCommit
    }
}

function Get-EdgeNotes {
    param([string]$TargetDir)
    $candidates = @(
        (Join-Path $TargetDir ".edge-notes.md"),
        (Join-Path $TargetDir "EDGE_NOTES.md"),
        (Join-Path $TargetDir ".github\EDGE_NOTES.md")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            try {
                $content = [System.IO.File]::ReadAllText($c, [System.Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
                if (-not [string]::IsNullOrWhiteSpace($content)) { return $content.Trim() }
            } catch {}
        }
    }
    return $null
}

function Get-DependencyHash {
    param([string]$TargetDir)
    $reqPath = Join-Path $TargetDir "requirements.txt"
    if (-not (Test-Path $reqPath)) { return "" }
    try {
        $hash = (Get-FileHash -Path $reqPath -Algorithm SHA256 -ErrorAction Stop).Hash
        return $hash.ToLowerInvariant()
    } catch { return "" }
}

function Get-NpmHash {
    param([string]$TargetDir)
    $base = Join-Path $TargetDir "tools\Messanger\whatsapp\BaileysServer"
    $pkgPath = Join-Path $base "package.json"
    $lockPath = Join-Path $base "package-lock.json"
    $combined = ""
    if (Test-Path $pkgPath) {
        try { $combined += (Get-FileHash -Path $pkgPath -Algorithm SHA256 -ErrorAction Stop).Hash } catch {}
    }
    if (Test-Path $lockPath) {
        try { $combined += (Get-FileHash -Path $lockPath -Algorithm SHA256 -ErrorAction Stop).Hash } catch {}
    }
    if (-not $combined) { return "" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($combined)
        $hashBytes = $sha.ComputeHash($bytes)
        return (-join ($hashBytes | ForEach-Object { $_.ToString("x2") }))
    } finally { $sha.Dispose() }
}

function Backup-UserDataForUpdate {
    param([string]$InstallPath)
    if (-not $InstallPath -or -not (Test-Path $InstallPath)) { return $null }
    $envFile = Join-Path $InstallPath ".env"
    $memoryDir = Join-Path $InstallPath "Data\jarvis_memory"
    $indexerDir = Join-Path $InstallPath "Data\jarvis_indexer"
    $mcpFile = Join-Path $InstallPath "Data\mcp_servers.json"
    $cookiesDir = Join-Path $InstallPath "Data\SessionCookies"
    $hasUserData = (Test-Path $envFile) -or (Test-Path $memoryDir) -or (Test-Path $indexerDir) -or (Test-Path $mcpFile) -or (Test-Path $cookiesDir)
    if (-not $hasUserData) {
        Write-Success "No user data present; skipping backup."
        return $null
    }
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupRoot = Join-Path $env:LOCALAPPDATA "Jarvis\Backups"
    if (-not (Test-Path $backupRoot)) {
        New-Item -ItemType Directory -Path $backupRoot -Force -ErrorAction SilentlyContinue | Out-Null
    }
    $backupFolder = Join-Path $backupRoot "Update_$timestamp"
    try {
        New-Item -ItemType Directory -Path $backupFolder -Force -ErrorAction Stop | Out-Null
        if (Test-Path $envFile) { Copy-Item -Path $envFile -Destination (Join-Path $backupFolder ".env") -Force -ErrorAction Stop }
        if (Test-Path $mcpFile) { Copy-Item -Path $mcpFile -Destination (Join-Path $backupFolder "mcp_servers.json") -Force -ErrorAction Stop }
        if (Test-Path $memoryDir) { Copy-Item -Path $memoryDir -Destination (Join-Path $backupFolder "jarvis_memory") -Recurse -Force -ErrorAction Stop }
        if (Test-Path $indexerDir) { Copy-Item -Path $indexerDir -Destination (Join-Path $backupFolder "jarvis_indexer") -Recurse -Force -ErrorAction Stop }
        if (Test-Path $cookiesDir) { Copy-Item -Path $cookiesDir -Destination (Join-Path $backupFolder "SessionCookies") -Recurse -Force -ErrorAction Stop }
        Write-Success "Backup saved: $backupFolder"
        Prune-OldBackups -BackupRoot $backupRoot -RetainCount 5
        return $backupFolder
    } catch {
        Write-Fail "Backup failed: $($_.Exception.Message)"
        return $null
    }
}

function Prune-OldBackups {
    param([string]$BackupRoot, [int]$RetainCount = 5)
    try {
        $dirs = Get-ChildItem -Path $BackupRoot -Directory -Filter "Update_*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
        if ($dirs.Count -le $RetainCount) { return }
        $toRemove = $dirs | Select-Object -Skip $RetainCount
        foreach ($d in $toRemove) {
            Remove-Item -Path $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Invoke-GitStashIfDirty {
    param([string]$TargetDir)
    $statusR = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("status", "--porcelain")
    if ($statusR.ExitCode -ne 0) { return $null }
    $out = "$($statusR.Output)".Trim()
    if ([string]::IsNullOrWhiteSpace($out)) { return $null }
    $stashMsg = "jarvis-pre-update-$(Get-Date -Format 'yyyyMMddHHmmss')"
    $r = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("stash", "push", "-u", "-m", $stashMsg)
    if ($r.ExitCode -eq 0) {
        Write-Success "Local modifications stashed as '$stashMsg'."
        return $stashMsg
    }
    return $null
}

function Invoke-GitStashRestore {
    param([string]$TargetDir, [string]$StashMessage)
    if ([string]::IsNullOrWhiteSpace($StashMessage)) { return }
    $listR = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("stash", "list")
    if ($listR.ExitCode -ne 0) { return }
    $matching = @($listR.Output | Where-Object { "$_" -match [regex]::Escape($StashMessage) })
    if ($matching.Count -eq 0) { return }
    $r = Invoke-GitCommand -WorkingDir $TargetDir -Arguments @("stash", "pop")
    if ($r.ExitCode -eq 0) {
        Write-Success "Local modifications restored."
    } else {
        Write-Warn "Could not restore local modifications due to conflicts. Stash kept at 'stash@{0}'."
    }
}

function Sync-PythonDependencies {
    param([string]$TargetDir, [string]$OldHash)
    $venvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Warn "Virtual environment missing; skipping Python dependency sync."
        return @{ Success = $false; NewHash = "" }
    }
    $newHash = Get-DependencyHash -TargetDir $TargetDir
    if ($newHash -and $newHash -eq $OldHash) {
        Write-Success "Python dependencies unchanged; skipping pip install."
        return @{ Success = $true; NewHash = $newHash }
    }
    $reqPath = Join-Path $TargetDir "requirements.txt"
    if (-not (Test-Path $reqPath)) {
        Write-Warn "requirements.txt not found; skipping pip install."
        return @{ Success = $true; NewHash = "" }
    }
    Write-Host "  -> requirements.txt changed; syncing Python packages..." -ForegroundColor Cyan
    Push-Location $TargetDir
    try {
        & $venvPython -m pip install --prefer-binary --timeout 100 --retries 5 -r requirements.txt 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            return @{ Success = $false; NewHash = $newHash }
        }
    } finally {
        Pop-Location
    }
    Write-Success "Python dependencies synchronized."
    return @{ Success = $true; NewHash = $newHash }
}

function Sync-NodeDependencies {
    param([string]$TargetDir, [string]$OldHash)
    $baileysPath = Join-Path $TargetDir "tools\Messanger\whatsapp\BaileysServer"
    if (-not (Test-Path $baileysPath)) {
        Write-Success "Baileys server not present; skipping Node dependency sync."
        return @{ Success = $true; NewHash = "" }
    }
    $newHash = Get-NpmHash -TargetDir $TargetDir
    if ($newHash -and $newHash -eq $OldHash) {
        Write-Success "Node dependencies unchanged; skipping npm install."
        return @{ Success = $true; NewHash = $newHash }
    }
    $npmExe = Get-NpmExecutable
    if (-not $npmExe) {
        Write-Warn "npm not found; skipping Node dependency sync."
        return @{ Success = $true; NewHash = $newHash }
    }
    Write-Host "  -> package.json changed; syncing Node packages..." -ForegroundColor Cyan
    $lockPath = Join-Path $baileysPath "package-lock.json"
    Push-Location $baileysPath
    try {
        if (Test-Path $lockPath) {
            & $npmExe ci --no-audit --no-fund 2>&1 | Out-Host
            if ($LASTEXITCODE -ne 0) {
                & $npmExe install --no-audit --no-fund 2>&1 | Out-Host
                if ($LASTEXITCODE -ne 0) {
                    return @{ Success = $false; NewHash = $newHash }
                }
            }
        } else {
            & $npmExe install --no-audit --no-fund 2>&1 | Out-Host
            if ($LASTEXITCODE -ne 0) {
                return @{ Success = $false; NewHash = $newHash }
            }
        }
    } finally {
        Pop-Location
    }
    Write-Success "Node dependencies synchronized."
    return @{ Success = $true; NewHash = $newHash }
}

function Test-Health {
    param([string]$TargetDir)
    $venvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        return @{ Healthy = $false; Reason = "Virtual environment Python not found." }
    }
    Push-Location $TargetDir
    try {
        & $venvPython -c "import sys; print(sys.version_info[:2])" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            return @{ Healthy = $false; Reason = "Virtual environment Python is not responding." }
        }
        $protocolFile = Join-Path $TargetDir "JarvisProtocol.py"
        if (Test-Path $protocolFile) {
            $importCheck = & $venvPython -c "import JarvisProtocol; print('ok')" 2>&1
            if ($LASTEXITCODE -ne 0) {
                return @{ Healthy = $false; Reason = "Core module import failed: $($importCheck -join ' ')" }
            }
        }
    } finally {
        Pop-Location
    }
    return @{ Healthy = $true; Reason = "" }
}

function Test-CliRegistration {
    try {
        $found = @(& where.exe jarvis 2>$null)
        return ($found.Count -gt 0)
    } catch { return $false }
}

function Register-Cli {
    param([string]$TargetDir)
    $venvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
    $registryScript = Join-Path $TargetDir "SetupRegistry.py"
    if (-not (Test-Path $venvPython)) {
        Write-Warn "Virtual environment missing; cannot re-register CLI."
        return $false
    }
    if (-not (Test-Path $registryScript)) {
        Write-Warn "SetupRegistry.py not found; skipping CLI registration."
        return $false
    }
    Push-Location $TargetDir
    try {
        & $venvPython $registryScript 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "SetupRegistry.py returned exit code $LASTEXITCODE."
            return $false
        }
    } finally {
        Pop-Location
    }
    Update-SessionPath
    Broadcast-EnvironmentChange
    Write-Success "CLI registration refreshed."
    return $true
}

function Invoke-Rollback {
    param(
        [string]$TargetDir,
        [string]$TargetRef,
        [string]$BackupFolder,
        $PreviousState
    )
    Write-Step "Rollback" "Restoring previous version ($TargetRef)..."
    Push-Location $TargetDir
    try {
        & git reset --hard $TargetRef 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Git reset to $TargetRef failed."
            return $false
        }
    } finally {
        Pop-Location
    }
    Write-Success "Code restored to $TargetRef."
    if ($BackupFolder -and (Test-Path $BackupFolder)) {
        $envBackup = Join-Path $BackupFolder ".env"
        if (Test-Path $envBackup) {
            Copy-Item -Path $envBackup -Destination (Join-Path $TargetDir ".env") -Force -ErrorAction SilentlyContinue
            Write-Success "User configuration restored from backup."
        }
    }
    $syncR = Sync-PythonDependencies -TargetDir $TargetDir -OldHash ""
    if (-not $syncR.Success) {
        Write-Fail "Dependency reinstall after rollback failed."
        return $false
    }
    if ($PreviousState) {
        $PreviousState.last_rollback_at = (Get-Date).ToUniversalTime().ToString("o")
        [void](Write-StateFile -TargetDir $TargetDir -State $PreviousState)
    }
    Write-Success "Rollback completed."
    return $true
}

function Show-EdgePrompt {
    param(
        $State,
        [int]$CooldownDays,
        [string]$EdgeNotes,
        [int]$AheadCount,
        [string]$LatestMessage,
        [string]$CurrentVersion
    )
    if (-not [Environment]::UserInteractive) { return "skip" }
    if ($State.edge_prompt_permanently_muted) { return "skip" }
    if ($State.last_edge_prompt_at) {
        try {
            $lastPrompt = [DateTime]::Parse($State.last_edge_prompt_at)
            $elapsed = (Get-Date).ToUniversalTime() - $lastPrompt.ToUniversalTime()
            if ($elapsed.TotalDays -lt $CooldownDays) { return "skip" }
        } catch {}
    }
    Write-Host ""
    Write-Host "  -----------------------------------------------------------------" -ForegroundColor DarkCyan
    Write-Host "  The developer's main branch has $AheadCount new commit(s)" -ForegroundColor White
    Write-Host "  since the latest stable release ($CurrentVersion)." -ForegroundColor White
    Write-Host ""
    if ($EdgeNotes) {
        Write-Host "  What's in development (curated by the maintainer):" -ForegroundColor Cyan
        foreach ($line in ($EdgeNotes -split "`r?`n")) {
            Write-Host "    $line" -ForegroundColor Gray
        }
    } elseif ($LatestMessage) {
        Write-Host "  Most recent commit: $LatestMessage" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  Power users can try these bleeding-edge changes before they are" -ForegroundColor DarkYellow
    Write-Host "  officially released as stable. Some features may be incomplete." -ForegroundColor DarkYellow
    Write-Host "  A backup is created automatically, and 'jarvis update --rollback'" -ForegroundColor DarkYellow
    Write-Host "  restores the previous stable version at any time." -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "    [1] Stay on stable channel (recommended)" -ForegroundColor Green
    Write-Host "    [2] Try edge build (power users)" -ForegroundColor Yellow
    Write-Host "    [3] Remind me in 30 days" -ForegroundColor Gray
    Write-Host "    [4] Never ask again" -ForegroundColor Gray
    Write-Host ""
    Clear-ConsoleInputBuffer
    while ($true) {
        $choice = Read-Host "  Choice [1]"
        if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "1" }
        $choice = $choice.Trim()
        switch ($choice) {
            "1" { return "stay" }
            "2" { return "edge" }
            "3" { return "remind" }
            "4" { return "mute" }
            default { Write-Host "  Invalid choice. Enter 1, 2, 3, or 4." -ForegroundColor DarkYellow }
        }
    }
}

function Invoke-CheckMode {
    param([string]$InstallPath, [bool]$SilentMode)
    $state = Read-StateFile -TargetDir $InstallPath
    if (-not $state) { $state = New-DefaultState }
    if (-not $state.channel) { $state.channel = "stable" }
    $currentCommit = Get-CurrentCommit -TargetDir $InstallPath
    $currentTag = Get-CurrentTag -TargetDir $InstallPath
    $currentVersion = if ($currentTag) { $currentTag } elseif ($state.version) { $state.version } else { $currentCommit.Substring(0, [Math]::Min(8, $currentCommit.Length)) }
    [void](Invoke-GitCommand -WorkingDir $InstallPath -Arguments @("fetch", "--tags", "--prune", "origin"))
    $latestTag = Get-LatestStableTag -TargetDir $InstallPath
    $edgeInfo = Get-EdgeInfo -TargetDir $InstallPath

    if (-not $SilentMode) {
        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "   J.A.R.V.I.S. Update Status                              " -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Install path    : $InstallPath" -ForegroundColor White
        Write-Host "  Current version : $currentVersion" -ForegroundColor White
        Write-Host "  Channel         : $($state.channel)" -ForegroundColor White
        Write-Host ""
        Write-Host "  Latest stable   : $(if ($latestTag) { $latestTag } else { 'not found' })" -ForegroundColor White
        if ($currentTag -and $latestTag -and $currentTag -ne $latestTag) {
            Write-Host "  Status          : Update available" -ForegroundColor Yellow
        } elseif ($state.channel -eq "edge") {
            Write-Host "  Status          : On edge channel" -ForegroundColor Yellow
        } else {
            Write-Host "  Status          : Up to date" -ForegroundColor Green
        }
        if ($edgeInfo) {
            Write-Host ""
            Write-Host "  Edge channel    : $($edgeInfo.AheadCount) commit(s) ahead of current build" -ForegroundColor Gray
            if ($edgeInfo.LatestMessage) {
                Write-Host "  Latest commit   : $($edgeInfo.LatestMessage)" -ForegroundColor Gray
            }
        }
        Write-Host ""
        Write-Host "  Run 'jarvis update' to apply any available updates." -ForegroundColor Cyan
        Write-Host ""
    } else {
        $status = if ($currentTag -and $latestTag -and $currentTag -ne $latestTag) { "update_available" } elseif ($state.channel -eq "edge") { "on_edge" } else { "up_to_date" }
        Write-Output "STATUS=$status CURRENT=$currentVersion LATEST=$latestTag CHANNEL=$($state.channel) EDGE_AHEAD=$($edgeInfo.AheadCount)"
    }
}

function Update-Jarvis {
    param(
        [string]$InstallPathOverride,
        [string]$ChannelOverride,
        [bool]$CheckOnly,
        [bool]$SilentMode,
        [bool]$AutoUpdateMode,
        [bool]$RollbackMode,
        [bool]$ForceMode,
        [int]$CooldownDays
    )

    if (-not $SilentMode) {
        Clear-Host
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "   J.A.R.V.I.S. OS Agent - Update Manager                  " -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Cyan
    }

    $installPath = Resolve-InstallPath -OverridePath $InstallPathOverride
    if (-not $installPath -or -not (Test-Path $installPath)) {
        Write-Fail "J.A.R.V.I.S. installation not found. Please run install.ps1 first."
        $script:ExitCode = 1
        return
    }
    if (-not (Test-Path (Join-Path $installPath ".git"))) {
        Write-Fail "Installation directory is not a Git repository. Reinstall required."
        $script:ExitCode = 1
        return
    }

    if ($CheckOnly) {
        Invoke-CheckMode -InstallPath $installPath -SilentMode $SilentMode
        return
    }

    $lock = Acquire-UpdateLock -TargetDir $installPath
    if (-not $lock.Acquired) {
        Write-Fail $lock.Reason
        $script:ExitCode = 1
        return
    }

    try {
        $state = Read-StateFile -TargetDir $installPath
        if (-not $state) { $state = New-DefaultState }
        if (-not $state.channel) { $state.channel = "stable" }

        if ($ChannelOverride) {
            if (-not $SilentMode) {
                Write-Info "Channel change requested: $($state.channel) -> $ChannelOverride"
            }
            $state.channel = $ChannelOverride
            [void](Write-StateFile -TargetDir $installPath -State $state)
            if (-not $SilentMode) { Write-Success "Channel set to '$ChannelOverride'." }
        }

        $currentChannel = $state.channel
        $currentCommit = Get-CurrentCommit -TargetDir $installPath
        $currentTag = Get-CurrentTag -TargetDir $installPath
        $currentVersion = if ($currentTag) { $currentTag } elseif ($state.version) { $state.version } else { $currentCommit.Substring(0, [Math]::Min(8, $currentCommit.Length)) }

        if (-not $SilentMode) {
            Write-Host ""
            Write-Host "  Install path : $installPath" -ForegroundColor White
            Write-Host "  Channel      : $currentChannel" -ForegroundColor White
            Write-Host "  Version      : $currentVersion" -ForegroundColor White
        }

        if ($RollbackMode) {
            if (-not $state.version -or -not $state.commit) {
                Write-Fail "No previous version recorded; cannot rollback automatically."
                Write-Warn "Inspect '$installPath' with 'git log' to identify a manual target."
                $script:ExitCode = 1
                return
            }
            $targetRef = $state.version
            if (-not $SilentMode) {
                if (-not (Request-Confirmation -Prompt "Rollback to $targetRef?" -DefaultYes $false)) {
                    Write-Warn "Rollback cancelled."
                    return
                }
            }
            $backupFolder = Backup-UserDataForUpdate -InstallPath $installPath
            Stop-JarvisProcesses -TargetDir $installPath
            $ok = Invoke-Rollback -TargetDir $installPath -TargetRef $targetRef -BackupFolder $backupFolder -PreviousState $state
            if (-not $ok) {
                Write-Fail "Rollback failed. Manual recovery may be required."
                $script:ExitCode = 1
            }
            return
        }

        Write-Step "1/7" "Fetching latest repository metadata..."
        $fetchR = Invoke-GitCommand -WorkingDir $installPath -Arguments @("fetch", "--tags", "--prune", "origin")
        if ($fetchR.ExitCode -ne 0) {
            Write-Fail "Failed to reach the remote repository. Check your internet connection."
            $script:ExitCode = 1
            return
        }
        Write-Success "Repository metadata refreshed."

        $latestTag = Get-LatestStableTag -TargetDir $installPath
        $edgeInfo = Get-EdgeInfo -TargetDir $installPath

        Write-Step "2/7" "Determining target version..."
        $targetRef = ""
        $targetVersion = ""
        $pendingChannelSwitch = ""

        switch ($currentChannel) {
            "stable" {
                if (-not $latestTag) {
                    Write-Warn "No stable release tag found on remote."
                    $targetRef = ""
                } elseif ($currentTag -eq $latestTag) {
                    $targetRef = ""
                } else {
                    $targetRef = $latestTag
                    $targetVersion = $latestTag
                }
            }
            "edge" {
                if (-not $edgeInfo -or $edgeInfo.AheadCount -eq 0) {
                    $targetRef = ""
                    if ($latestTag -and $currentTag -ne $latestTag) {
                        Write-Warn "A newer stable release ($latestTag) is available."
                        if (-not $SilentMode -and -not $AutoUpdateMode) {
                            if (Read-YesNo "Switch to stable release $latestTag?" "N" -eq "Y") {
                                $pendingChannelSwitch = "stable"
                                $targetRef = $latestTag
                                $targetVersion = $latestTag
                            }
                        }
                    }
                } else {
                    $targetRef = "origin/main"
                    $targetVersion = "edge-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
                }
            }
            "pinned" {
                if (-not $SilentMode) { Write-Success "Channel is pinned. No automatic updates applied." }
                return
            }
        }

        if (-not $targetRef) {
            if ($currentChannel -eq "stable" -and $edgeInfo -and $edgeInfo.AheadCount -gt 0) {
                if ($AutoUpdateMode) {
                    if (-not $SilentMode) { Write-Success "Stable channel is up to date." }
                    return
                }
                $edgeNotes = Get-EdgeNotes -TargetDir $installPath
                $decision = Show-EdgePrompt -State $state -CooldownDays $CooldownDays -EdgeNotes $edgeNotes -AheadCount $edgeInfo.AheadCount -LatestMessage $edgeInfo.LatestMessage -CurrentVersion $currentVersion
                $nowIso = (Get-Date).ToUniversalTime().ToString("o")
                switch ($decision) {
                    "skip" {
                        if (-not $SilentMode) { Write-Success "Stable channel is up to date." }
                        return
                    }
                    "stay" {
                        $state.last_edge_prompt_at = $nowIso
                        $state.edge_prompt_dismissed_count = [int]$state.edge_prompt_dismissed_count + 1
                        [void](Write-StateFile -TargetDir $installPath -State $state)
                        Write-Success "Staying on stable channel."
                        return
                    }
                    "remind" {
                        $state.last_edge_prompt_at = $nowIso
                        [void](Write-StateFile -TargetDir $installPath -State $state)
                        Write-Success "Reminder set. Stable channel is up to date."
                        return
                    }
                    "mute" {
                        $state.edge_prompt_permanently_muted = $true
                        $state.last_edge_prompt_at = $nowIso
                        [void](Write-StateFile -TargetDir $installPath -State $state)
                        Write-Success "Edge prompts disabled. Stable channel is up to date."
                        return
                    }
                    "edge" {
                        $state.channel = "edge"
                        $state.last_edge_prompt_at = $nowIso
                        [void](Write-StateFile -TargetDir $installPath -State $state)
                        $currentChannel = "edge"
                        $targetRef = "origin/main"
                        $targetVersion = "edge-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
                        Write-Success "Switching to edge channel."
                    }
                }
            } else {
                if (-not $SilentMode) { Write-Success "Already on the latest version for '$currentChannel' channel." }
                return
            }
        }

        if (-not $SilentMode) {
            Write-Host ""
            Write-Host "  Target version : $targetVersion" -ForegroundColor White
            if ($currentChannel -eq "edge") {
                Write-Host "  Channel        : edge" -ForegroundColor White
            }
            if ($pendingChannelSwitch) {
                Write-Host "  Channel switch : $currentChannel -> $pendingChannelSwitch" -ForegroundColor Yellow
            }
        }

        if ($currentChannel -eq "stable" -and $latestTag -and $currentTag -ne $latestTag) {
            $changelogR = Invoke-GitCommand -WorkingDir $installPath -Arguments @("log", "$currentTag..$latestTag", "--oneline", "--no-merges", "-n", "15")
            if ($changelogR.ExitCode -eq 0 -and $changelogR.Output) {
                Write-Host ""
                Write-Host "  Changes in this release:" -ForegroundColor Cyan
                foreach ($line in $changelogR.Output) {
                    if (-not [string]::IsNullOrWhiteSpace("$line")) {
                        Write-Host "    $line" -ForegroundColor Gray
                    }
                }
            }
        }

        if (-not $SilentMode -and -not $AutoUpdateMode) {
            if (-not (Request-Confirmation -Prompt "Proceed with update to $targetVersion?" -DefaultYes $true)) {
                Write-Warn "Update cancelled."
                return
            }
        }

        $stashMessage = $null
        if ($currentChannel -eq "edge") {
            $stashMessage = Invoke-GitStashIfDirty -TargetDir $installPath
        }

        Write-Step "3/7" "Creating safety backup of user data..."
        $backupFolder = Backup-UserDataForUpdate -InstallPath $installPath

        $previousState = [pscustomobject]@{
            channel                     = $state.channel
            version                     = $currentVersion
            commit                      = $currentCommit
            deps_hash                   = $state.deps_hash
            npm_hash                    = $state.npm_hash
            last_edge_prompt_at         = $state.last_edge_prompt_at
            edge_prompt_dismissed_count = $state.edge_prompt_dismissed_count
            edge_prompt_permanently_muted = $state.edge_prompt_permanently_muted
            last_rollback_at            = $state.last_rollback_at
            last_updated_at             = $state.last_updated_at
        }
        $rollbackRef = if ($currentTag) { $currentTag } else { $currentCommit }

        Write-Step "4/7" "Stopping active J.A.R.V.I.S. processes..."
        Stop-JarvisProcesses -TargetDir $installPath

        Write-Step "5/7" "Applying update to $targetVersion..."
        $checkoutR = Invoke-GitCommand -WorkingDir $installPath -Arguments @("checkout", "--force", $targetRef)
        if ($checkoutR.ExitCode -ne 0) {
            $resetR = Invoke-GitCommand -WorkingDir $installPath -Arguments @("reset", "--hard", $targetRef)
            if ($resetR.ExitCode -ne 0) {
                Write-Fail "Failed to apply update. Manual recovery may be required."
                Write-Warn "Reverting to $rollbackRef ..."
                [void](Invoke-Rollback -TargetDir $installPath -TargetRef $rollbackRef -BackupFolder $backupFolder -PreviousState $previousState)
                $script:ExitCode = 1
                return
            }
        }
        $appliedCommit = Get-CurrentCommit -TargetDir $installPath
        Write-Success "Code updated to $targetVersion ($($appliedCommit.Substring(0, [Math]::Min(8, $appliedCommit.Length))))."

        Write-Step "6/7" "Synchronizing dependencies..."
        $pySync = Sync-PythonDependencies -TargetDir $installPath -OldHash $state.deps_hash
        if (-not $pySync.Success) {
            Write-Fail "Python dependency sync failed; rolling back..."
            [void](Invoke-Rollback -TargetDir $installPath -TargetRef $rollbackRef -BackupFolder $backupFolder -PreviousState $previousState)
            $script:ExitCode = 1
            return
        }
        $npmSync = Sync-NodeDependencies -TargetDir $installPath -OldHash $state.npm_hash
        if (-not $npmSync.Success) {
            Write-Warn "Node dependency sync reported issues. Continuing with health check."
        }

        Write-Step "7/7" "Verifying installation health..."
        $health = Test-Health -TargetDir $installPath
        if (-not $health.Healthy) {
            Write-Fail "Health check failed: $($health.Reason)"
            Write-Warn "Rolling back to $rollbackRef ..."
            $rbOk = Invoke-Rollback -TargetDir $installPath -TargetRef $rollbackRef -BackupFolder $backupFolder -PreviousState $previousState
            if ($rbOk) {
                Write-Success "System restored to previous working state."
            } else {
                Write-Fail "Automatic rollback did not complete. Please reinstall if issues persist."
            }
            $script:ExitCode = 1
            return
        }
        Write-Success "Health check passed."

        if (-not (Test-CliRegistration)) {
            Write-Info "Global CLI shim missing; re-registering..."
            [void](Register-Cli -TargetDir $installPath)
        }

        if ($stashMessage) {
            Invoke-GitStashRestore -TargetDir $installPath -StashMessage $stashMessage
        }

        $newState = [pscustomobject]@{
            channel                     = if ($pendingChannelSwitch) { $pendingChannelSwitch } else { $currentChannel }
            version                     = if ($targetVersion -and $targetVersion -notlike "edge-*") { $targetVersion } else { $currentVersion }
            commit                      = $appliedCommit
            deps_hash                   = $pySync.NewHash
            npm_hash                    = $npmSync.NewHash
            last_edge_prompt_at         = $state.last_edge_prompt_at
            edge_prompt_dismissed_count = $state.edge_prompt_dismissed_count
            edge_prompt_permanently_muted = $state.edge_prompt_permanently_muted
            last_rollback_at            = $state.last_rollback_at
            last_updated_at             = (Get-Date).ToUniversalTime().ToString("o")
        }
        [void](Write-StateFile -TargetDir $installPath -State $newState)

        if (-not $SilentMode) {
            Write-Host ""
            Write-Host "==========================================================" -ForegroundColor Green
            Write-Host "      J.A.R.V.I.S. Update Completed Successfully!         " -ForegroundColor Green
            Write-Host "==========================================================" -ForegroundColor Green
            Write-Host "  Version   : $targetVersion" -ForegroundColor White
            Write-Host "  Channel   : $($newState.channel)" -ForegroundColor White
            Write-Host "  Backup    : $backupFolder" -ForegroundColor White
            Write-Host ""
            Write-Host "  Rollback command : jarvis update --rollback" -ForegroundColor Cyan
            Write-Host ""
        }
    } finally {
        Release-UpdateLock -LockPath $lock.Path
    }
}

Update-Jarvis `
    -InstallPathOverride $InstallPath `
    -ChannelOverride $Channel `
    -CheckOnly ([bool]$Check) `
    -SilentMode ([bool]$Silent) `
    -AutoUpdateMode ([bool]$AutoUpdate) `
    -RollbackMode ([bool]$Rollback) `
    -ForceMode ([bool]$Force) `
    -CooldownDays $EdgePromptCooldownDays

exit $script:ExitCode