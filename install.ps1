$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
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

function Broadcast-EnvironmentChange {
    try {
        $result = [UIntPtr]::Zero
        [JarvisWin32]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null
    } catch {}
}

function Clear-VenvSessionVars {
    foreach ($v in @("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PYTHONHOME", "PYTHONPATH")) {
        if (Test-Path "Env:\$v") {
            Remove-Item "Env:\$v" -ErrorAction SilentlyContinue
        }
    }
}

function Clear-ConsoleInputBuffer {
    try {
        while ([Console]::KeyAvailable) {
            [void][Console]::ReadKey($true)
        }
    } catch {}
}

function Update-SessionPath {
    try {
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $currentPath = $env:Path

        $extraPaths = @(
            "$env:LOCALAPPDATA\Programs\Python\Python311",
            "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
            "$env:ProgramFiles\Python311",
            "$env:ProgramFiles\Python311\Scripts",
            "C:\Python311",
            "C:\Python311\Scripts",
            "$env:LOCALAPPDATA\Programs\nodejs",
            "$env:ProgramFiles\nodejs",
            "$env:APPDATA\npm",
            "$env:ProgramFiles\Git\cmd"
        )

        $combined = @()
        $seen = @{}

        foreach ($p in $extraPaths) {
            if ($p -and (Test-Path $p)) {
                $norm = $p.TrimEnd('\').ToLowerInvariant()
                if (-not $seen.ContainsKey($norm)) {
                    $seen[$norm] = $true
                    $combined += $p
                }
            }
        }

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

function Download-FileFast {
    param([string]$Url, [string]$OutFile)
    if (Test-Path $OutFile) {
        Remove-Item -Path $OutFile -Force -ErrorAction SilentlyContinue
    }
    $curlCmd = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($curlCmd) {
        & $curlCmd.Source -fL --retry 3 --connect-timeout 15 -o $OutFile $Url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 0)) {
            return $true
        }
    }
    $prevPref = $ProgressPreference
    try {
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
        return ((Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 0))
    } catch {
        return $false
    } finally {
        $ProgressPreference = $prevPref
    }
}

function Test-VcRedistInstalled {
    $regPaths = @(
        "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        "HKLM:\SOFTWARE\Wow6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
    )
    $regInstalled = $false
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) {
            $props = Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue
            if ($null -ne $props -and $props.Installed -eq 1 -and $props.Minor -ge 30) {
                $regInstalled = $true
                break
            }
        }
    }
    $dll1 = Join-Path $env:SystemRoot "System32\vcruntime140.dll"
    $dll2 = Join-Path $env:SystemRoot "System32\vcruntime140_1.dll"
    return ($regInstalled -and (Test-Path $dll1) -and (Test-Path $dll2))
}

function Test-IsPython311 {
    param([string]$ExePath)
    if ([string]::IsNullOrWhiteSpace($ExePath) -or -not (Test-Path $ExePath)) {
        return $false
    }
    if ($ExePath -match "WindowsApps") {
        return $false
    }
    $check = & $ExePath -c "import sys, struct; print(1 if (sys.version_info.major == 3 and sys.version_info.minor == 11 and struct.calcsize('P') * 8 == 64) else 0)" 2>$null
    return ($LASTEXITCODE -eq 0 -and "$check".Trim() -eq "1")
}

function Get-ValidPython {
    $knownPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "C:\Python311\python.exe"
    )
    foreach ($candidate in $knownPaths) {
        if (Test-IsPython311 -ExePath $candidate) {
            return $candidate
        }
    }

    $pyLauncher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $exePath = & py -3.11-64 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $exePath) {
            $exePath = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        }
        if ($LASTEXITCODE -eq 0 -and $exePath) {
            $trimmed = "$exePath".Trim()
            if (Test-IsPython311 -ExePath $trimmed) {
                return $trimmed
            }
        }
    }

    foreach ($cmd in @("python", "python3")) {
        $found = Get-Command $cmd -CommandType Application -ErrorAction SilentlyContinue
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

function Test-NodeVersion {
    Update-SessionPath
    $nodeCmd = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $nodeCmd) {
        $fallbacks = @(
            "$env:LOCALAPPDATA\Programs\nodejs\node.exe",
            "$env:ProgramFiles\nodejs\node.exe"
        )
        foreach ($fb in $fallbacks) {
            if (Test-Path $fb) {
                $env:Path = "$(Split-Path $fb);$env:Path"
                $nodeCmd = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue
                if ($nodeCmd) { break }
            }
        }
    }
    $npmExe = Get-NpmExecutable
    if (-not $nodeCmd -or -not $npmExe) {
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
            $targetRelease = $releases | Where-Object { $_.lts -ne $false } | Select-Object -First 1
            if (-not $targetRelease) {
                $targetRelease = $releases[0]
            }
            $latestVer = $targetRelease.version.TrimStart("v")
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
    $fallbackVer = "22.14.0"
    return @{
        Version = $fallbackVer
        Url     = "https://nodejs.org/dist/v$fallbackVer/node-v$fallbackVer-x64.msi"
    }
}

function Test-WingetAvailable {
    $winget = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue
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
    if (-not $TargetDir -or -not (Test-Path $TargetDir)) { return }
    $normalizedTarget = ""
    try {
        $normalizedTarget = [System.IO.Path]::GetFullPath($TargetDir).TrimEnd('\').ToLowerInvariant()
    } catch { return }
    $targetWithSlash = $normalizedTarget + '\'
    $allowedNames = @("python.exe", "pythonw.exe", "node.exe", "jarvis.exe", "pip.exe")
    $killedCount = 0

    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if ($_.ProcessId -eq $PID) { return $false }
        $procName = if ($_.Name) { $_.Name.ToLowerInvariant() } else { "" }
        $exePath = if ($_.ExecutablePath) { $_.ExecutablePath.ToLowerInvariant() } else { "" }
        $cmdLine = if ($_.CommandLine) { $_.CommandLine.ToLowerInvariant() } else { "" }

        if ($exePath.StartsWith($targetWithSlash)) {
            return $true
        }
        if ($allowedNames -contains $procName) {
            if ($cmdLine.Contains($targetWithSlash) -or $cmdLine.Contains("jarvisprotocol.py") -or $cmdLine.Contains("baileysserver")) {
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

    foreach ($lf in @(".jarvis.lock", "jarvis.lock")) {
        $lockFile = Join-Path $TargetDir $lf
        if (Test-Path $lockFile) {
            Remove-Item -Path $lockFile -Force -ErrorAction SilentlyContinue
        }
    }

    if ($killedCount -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Read-Utf8FileClean {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return "" }
    try {
        $raw = [System.IO.File]::ReadAllText($FilePath, [System.Text.Encoding]::UTF8)
        if ($null -eq $raw) { return "" }
        return $raw.TrimStart([char]0xFEFF)
    } catch {
        return ""
    }
}

function Write-Utf8NoBom {
    param([string]$FilePath, [string]$Content)
    $clean = if ($null -ne $Content) { $Content.TrimStart([char]0xFEFF) } else { "" }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FilePath, $clean, $utf8NoBom)
}

function Set-EnvValue {
    param([string]$FilePath, [string]$Key, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return
    }
    $content = Read-Utf8FileClean -FilePath $FilePath
    $pattern = "(?m)^" + [regex]::Escape($Key) + "\s*=[^\r\n]*"
    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "$Key=$Value" })
    } else {
        if ([string]::IsNullOrWhiteSpace($content)) {
            $content = "$Key=$Value`r`n"
        } else {
            $content = $content.TrimEnd("`r", "`n") + "`r`n$Key=$Value`r`n"
        }
    }
    Write-Utf8NoBom -FilePath $FilePath -Content $content
}

function Clear-EnvValue {
    param([string]$FilePath, [string]$Key, [switch]$OnlyIfPlaceholder)
    if (-not (Test-Path $FilePath)) { return }
    $content = Read-Utf8FileClean -FilePath $FilePath
    if ([string]::IsNullOrEmpty($content)) { return }
    $pattern = "(?m)^" + [regex]::Escape($Key) + "\s*=([^\r\n]*)"
    $m = [regex]::Match($content, $pattern)
    if (-not $m.Success) { return }
    $current = $m.Groups[1].Value.Trim()
    if ($OnlyIfPlaceholder -and $current -ne "your_key_here" -and $current -ne "your_key") { return }
    $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($match) "$Key=" })
    Write-Utf8NoBom -FilePath $FilePath -Content $content
}

function Get-EnvVal {
    param([string]$Content, [string]$Key)
    if ([string]::IsNullOrEmpty($Content)) { return "" }
    $clean = $Content.TrimStart([char]0xFEFF)
    $m = [regex]::Match($clean, "(?m)^" + [regex]::Escape($Key) + "\s*=([^\r\n]*)")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ""
}

function Get-EffectiveDefault {
    param([string]$Content, [string]$Key, [string]$FallbackDefault)
    $existing = Get-EnvVal -Content $Content -Key $Key
    if (-not [string]::IsNullOrWhiteSpace($existing) -and $existing -ne "your_key_here" -and $existing -ne "your_key") {
        return $existing
    }
    return $FallbackDefault
}

function Save-OrPreserveEnvKey {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$NewValue,
        [switch]$SilentSkip
    )
    if (-not [string]::IsNullOrWhiteSpace($NewValue)) {
        Set-EnvValue -FilePath $FilePath -Key $Key -Value $NewValue
        Write-Success "$Key set."
        return @{ Configured = $true; EffectiveValue = $NewValue }
    }
    Clear-EnvValue -FilePath $FilePath -Key $Key -OnlyIfPlaceholder
    $after = Get-EnvVal -Content (Read-Utf8FileClean -FilePath $FilePath) -Key $Key
    if (-not [string]::IsNullOrWhiteSpace($after)) {
        Write-Success "$Key kept existing value."
        return @{ Configured = $true; EffectiveValue = $after }
    }
    if (-not $SilentSkip) {
        Write-Warn "$Key skipped."
    }
    return @{ Configured = $false; EffectiveValue = $null }
}

function Read-EnvInput {
    param(
        [string]$Label,
        [string]$Default = "",
        [bool]$AllowSkip = $false
    )
    if (-not [Environment]::UserInteractive) {
        if (-not [string]::IsNullOrWhiteSpace($Default)) { return $Default }
        return $null
    }
    $prompt = "  $Label"
    if (-not [string]::IsNullOrWhiteSpace($Default)) {
        $prompt += " [default: $Default]"
    }
    $prompt += ": "
    Clear-ConsoleInputBuffer
    while ($true) {
        $userInput = Read-Host $prompt
        if ([string]::IsNullOrWhiteSpace($userInput)) {
            if (-not [string]::IsNullOrWhiteSpace($Default)) { return $Default }
            if ($AllowSkip) { return $null }
            Write-Host "    [!] Value required (or type 's' to skip)." -ForegroundColor DarkYellow
            continue
        }
        $trimmed = $userInput.Trim()
        if ($trimmed -eq "s" -or $trimmed -eq "skip") {
            if ($AllowSkip) { return $null }
            if (-not [string]::IsNullOrWhiteSpace($Default)) { return $Default }
            return $null
        }
        return $trimmed
    }
}

function Read-YesNo {
    param(
        [string]$Question,
        [string]$Default = "N"
    )
    if (-not [Environment]::UserInteractive) {
        return $Default
    }
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

function Read-KeyWithReuse {
    param(
        [string]$GroupName,
        [string]$SourceKey,
        [string]$SourceEndpoint,
        [string]$SourceModel,
        [string]$DefaultEndpoint,
        [string]$DefaultModel
    )
    if (-not [string]::IsNullOrWhiteSpace($SourceKey)) {
        $reuse = Read-YesNo "Same as Fast Brain for $GroupName (key + endpoint + model)?" "Y"
        if ($reuse -eq "Y") {
            return @{ Key = $SourceKey; Endpoint = $SourceEndpoint; Model = $SourceModel }
        }
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

    Clear-VenvSessionVars

    Write-Step "1/7" "Verifying System Prerequisites..."
    Update-SessionPath

    if (-not (Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-Warn "Git not found."
        if (-not (Install-WithWinget -PackageId "Git.Git" -DisplayName "Git")) {
            Write-Fail "Git is required. Install from https://git-scm.com/download/win and re-run."
            return
        }
        Start-Sleep -Seconds 2
        Update-SessionPath
    }
    if (-not (Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) {
        Write-Fail "Git executable still not detected in PATH. Please restart PowerShell and try again."
        return
    }
    Write-Success "Git detected."

    $vcRebootRequired = $false
    if (-not (Test-VcRedistInstalled)) {
        Write-Warn "Microsoft Visual C++ Redistributable (x64) not found or outdated. Auto-installing..."
        $vcUrl = "https://aka.ms/vs/16/release/vc_redist.x64.exe"
        $vcExe = Join-Path $env:TEMP "vc_redist.x64.exe"
        $vcInstalled = $false

        Write-Host "  -> Downloading vc_redist.x64.exe (~24 MB)..." -ForegroundColor Cyan
        if (Download-FileFast -Url $vcUrl -OutFile $vcExe) {
            Write-Host "  -> Running Visual C++ Redistributable installer (accept UAC prompt if shown)..." -ForegroundColor Cyan
            $vcExit = -1
            try {
                $vcProc = Start-Process -FilePath $vcExe -ArgumentList "/install", "/quiet", "/norestart" -Verb RunAs -Wait -PassThru -ErrorAction Stop
                $vcExit = $vcProc.ExitCode
            } catch {
                try {
                    $vcProc = Start-Process -FilePath $vcExe -ArgumentList "/install", "/passive", "/norestart" -Wait -PassThru -ErrorAction Stop
                    $vcExit = $vcProc.ExitCode
                } catch {}
            }
            Remove-Item -Path $vcExe -Force -ErrorAction SilentlyContinue

            if ($vcExit -eq 0 -or $vcExit -eq 1638) {
                $vcInstalled = $true
            } elseif ($vcExit -eq 3010) {
                $vcInstalled = $true
                $vcRebootRequired = $true
            }
        } else {
            Write-Warn "Direct download of vc_redist.x64.exe failed."
        }

        if (-not $vcInstalled -and -not (Test-VcRedistInstalled) -and (Test-WingetAvailable)) {
            Write-Warn "Attempting winget fallback for Visual C++ Redistributable..."
            if (Install-WithWinget -PackageId "Microsoft.VCRedist.2015+.x64" -DisplayName "Microsoft Visual C++ 2015-2022 Redistributable (x64)") {
                $vcInstalled = $true
            }
        }

        if (-not $vcInstalled -and -not (Test-VcRedistInstalled)) {
            Write-Fail "Visual C++ Redistributable (x64) could not be installed automatically."
            Write-Fail "Manual install: https://aka.ms/vs/16/release/vc_redist.x64.exe"
            return
        }
    }
    if ($vcRebootRequired) {
        Write-Success "Visual C++ Redistributable (x64) installed (system reboot recommended after setup)."
    } else {
        Write-Success "Visual C++ Redistributable (x64) verified."
    }

    $sysPython = Get-ValidPython
    if (-not $sysPython) {
        Write-Warn "64-bit Python 3.11 not found. Auto-installing Python 3.11.4 (64-bit)..."
        $pyVersion = "3.11.4"
        $pyInstaller = Join-Path $env:TEMP "python-$pyVersion-amd64.exe"
        $pyUrl = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-amd64.exe"

        Write-Host "  -> Downloading Python $pyVersion (~25 MB)..." -ForegroundColor Cyan
        if (Download-FileFast -Url $pyUrl -OutFile $pyInstaller) {
            Write-Host "  -> Running silent Python $pyVersion installer..." -ForegroundColor Cyan
            Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_launcher=1" -Wait -PassThru | Out-Null
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
            Write-Fail "Python 3.11 (64-bit) could not be installed automatically."
            Write-Fail "Manual install: https://www.python.org/ftp/python/3.11.4/python-3.11.4-amd64.exe"
            return
        }
    }
    $pyVerStr = & $sysPython --version 2>&1
    Write-Success "Python detected ($pyVerStr at $sysPython)."

    if (-not (Test-NodeVersion)) {
        Write-Warn "Node.js not found. Installing portable user-scope Node.js (no admin)..."

        $nodeInfo = Get-LatestNodeMsiInfo
        $nodeVer = $nodeInfo.Version
        $nodeZipUrl = "https://nodejs.org/dist/v$nodeVer/node-v$nodeVer-win-x64.zip"
        $nodeZipPath = Join-Path $env:TEMP "node-v$nodeVer-win-x64.zip"
        $nodeInstallDir = Join-Path $env:LOCALAPPDATA "Programs\nodejs"

        Write-Host "  -> Downloading Node.js v$nodeVer portable ZIP (~30 MB)..." -ForegroundColor Cyan
        if (Download-FileFast -Url $nodeZipUrl -OutFile $nodeZipPath) {
            Write-Host "  -> Extracting Node.js to $nodeInstallDir..." -ForegroundColor Cyan
            if (Test-Path $nodeInstallDir) {
                Remove-Item -Path $nodeInstallDir -Recurse -Force -ErrorAction SilentlyContinue
            }
            New-Item -ItemType Directory -Path $nodeInstallDir -Force | Out-Null

            $nodeExtractTemp = Join-Path $env:TEMP "node-extract-$([Guid]::NewGuid().ToString('N'))"
            try {
                Expand-Archive -Path $nodeZipPath -DestinationPath $nodeExtractTemp -Force -ErrorAction Stop
                $nodeInnerDir = Get-ChildItem -Path $nodeExtractTemp -Directory | Select-Object -First 1
                if ($nodeInnerDir) {
                    Copy-Item -Path (Join-Path $nodeInnerDir.FullName '*') -Destination $nodeInstallDir -Recurse -Force
                } else {
                    Copy-Item -Path (Join-Path $nodeExtractTemp '*') -Destination $nodeInstallDir -Recurse -Force
                }
            } catch {
                Write-Warn "Node.js ZIP extraction failed: $($_.Exception.Message)"
            } finally {
                Remove-Item -Path $nodeExtractTemp -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -Path $nodeZipPath -Force -ErrorAction SilentlyContinue
            }

            $nodeUserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
            if ($nodeUserPath -notlike "*$nodeInstallDir*") {
                [System.Environment]::SetEnvironmentVariable("Path", "$nodeUserPath;$nodeInstallDir", "User")
            }
            $env:Path = "$nodeInstallDir;$env:Path"
            Start-Sleep -Seconds 1
        } else {
            Write-Warn "Node.js portable ZIP download failed."
        }

        if (-not (Test-NodeVersion)) {
            Write-Fail "Node.js could not be installed automatically without admin."
            Write-Fail "Manual install: https://nodejs.org/en/download (Windows Binary .zip), extract to $nodeInstallDir and add to user PATH."
            return
        }
    }

    $npmPrefix = Join-Path $env:APPDATA "npm"
    $npmCache = Join-Path $env:LOCALAPPDATA "npm-cache"
    if (-not (Test-Path $npmPrefix)) { New-Item -ItemType Directory -Path $npmPrefix -Force | Out-Null }
    if (-not (Test-Path $npmCache)) { New-Item -ItemType Directory -Path $npmCache -Force | Out-Null }
    $npmExeForConfig = Get-NpmExecutable
    if ($npmExeForConfig) {
        & $npmExeForConfig config set prefix "$npmPrefix" 2>&1 | Out-Null
        & $npmExeForConfig config set cache "$npmCache" 2>&1 | Out-Null
        Write-Success "npm global prefix set to $npmPrefix."
    } else {
        Write-Warn "npm executable not found; skipping global prefix configuration."
    }
    $npmUserPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if ($npmUserPath -notlike "*$npmPrefix*") {
        [System.Environment]::SetEnvironmentVariable("Path", "$npmUserPath;$npmPrefix", "User")
    }
    $env:Path = "$npmPrefix;$env:Path"

    $nodeVerStr = & node.exe --version 2>&1
    Write-Success "Node.js detected ($nodeVerStr)."

    Write-Step "2/7" "Syncing J.A.R.V.I.S. OS Agent Repository..."
    $installPath = Join-Path $HOME "Jarvis-OS-Agent"
    $repoUrl = "https://github.com/thekaifansari01/Jarvis-OS-Agent.git"

    Stop-RunningJarvis -TargetDir $installPath

    $hasValidGitRepo = (Test-Path (Join-Path $installPath ".git")) -and (Test-Path (Join-Path $installPath "requirements.txt"))
    if ($hasValidGitRepo) {
        Write-Host "  -> Existing repository found at $installPath. Fetching updates..." -ForegroundColor Cyan
        Push-Location $installPath
        try {
            & git fetch --tags --prune origin main 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Could not reach remote repository; continuing with local codebase."
            } else {
                & git pull --ff-only origin main
                if ($LASTEXITCODE -ne 0) {
                    Write-Warn "Local modifications detected. Preserving local working tree."
                } else {
                    Write-Success "Repository updated to latest commit."
                }
            }
        } finally {
            Pop-Location
        }
    } else {
        if (Test-Path $installPath) {
            $backupPath = "${installPath}_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Write-Warn "Incomplete or non-git folder exists at $installPath. Moving to $backupPath..."
            Move-Item -Path $installPath -Destination $backupPath -Force -ErrorAction Stop
        }
        Write-Host "  -> Cloning into $installPath..." -ForegroundColor Cyan
        & git clone --depth 1 $repoUrl $installPath
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $installPath "requirements.txt"))) {
            Write-Fail "Failed to clone repository. Check your internet connection."
            return
        }
        Push-Location $installPath
        try {
            & git fetch --tags origin 2>&1 | Out-Null
        } finally {
            Pop-Location
        }
        Write-Success "Repository cloned successfully."
    }

    Push-Location $installPath
    try {
        Write-Step "3/7" "Configuring Isolated Python 3.11 Virtual Environment (.venv)..."
        $venvPython = Join-Path $installPath ".venv\Scripts\python.exe"

        if (Test-Path $venvPython) {
            if (-not (Test-IsPython311 -ExePath $venvPython)) {
                Write-Warn "Existing .venv is broken or not running 64-bit Python 3.11. Recreating..."
                & cmd.exe /c "rmdir /s /q `".venv`"" 2>$null
                if (Test-Path ".venv") {
                    Remove-Item -Path ".venv" -Recurse -Force -ErrorAction SilentlyContinue
                }
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

        Write-Step "4/7" "Installing Python Dependencies & AI Models (5-10 mins on first run)..."
        Write-Host "  -> Upgrading pip, setuptools, and wheel..." -ForegroundColor DarkGray
        & $venvPython -m pip install --upgrade pip setuptools wheel --quiet --timeout 100 --retries 5
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Pip self-upgrade reported a warning; continuing with dependency installation..."
        }

        Write-Host "  -> Installing packages from requirements.txt (CPU-optimized PyTorch)..." -ForegroundColor DarkGray
        & $venvPython -m pip install --prefer-binary --timeout 100 --retries 5 -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Python dependency installation failed. Check the error output above."
            return
        }
        Write-Success "All Python packages installed and verified."

        Write-Step "5/7" "Installing Node.js Dependencies for WhatsApp Baileys Bridge..."
        $baileysPath = Join-Path $installPath "tools\Messanger\whatsapp\BaileysServer"
        if (Test-Path $baileysPath) {
            Push-Location $baileysPath
            try {
                $npmExe = Get-NpmExecutable
                if (-not $npmExe) {
                    Write-Fail "npm executable not found in PATH."
                    return
                }
                & $npmExe install --no-audit --no-fund
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

        Write-Step "6/7" "Configuring Environment (.env) & API Keys..."
        $envFile = Join-Path $installPath ".env"
        $envExample = Join-Path $installPath ".env.example"

        if (-not (Test-Path $envFile)) {
            if (Test-Path $envExample) {
                $exampleClean = Read-Utf8FileClean -FilePath $envExample
                Write-Utf8NoBom -FilePath $envFile -Content $exampleClean
                Write-Success "Initialized .env from .env.example."
            } else {
                Write-Utf8NoBom -FilePath $envFile -Content ""
                Write-Warn "Created empty .env file (.env.example was not found)."
            }
        } else {
            $existingClean = Read-Utf8FileClean -FilePath $envFile
            Write-Utf8NoBom -FilePath $envFile -Content $existingClean
            Write-Success "Existing .env configuration preserved."
        }

        if ([Environment]::UserInteractive) {
            Clear-ConsoleInputBuffer
            $existingRaw = Read-Utf8FileClean -FilePath $envFile
            $existingFbKey = Get-EnvVal -Content $existingRaw -Key "FAST_BRAIN_API_KEY"
            $promptDefault = if ([string]::IsNullOrWhiteSpace($existingFbKey) -or $existingFbKey -eq "your_key_here" -or $existingFbKey -eq "your_key") { "Y" } else { "N" }

            Write-Host ""
            $configureNow = Read-YesNo "Would you like to configure your API keys now?" $promptDefault
            if ($configureNow -eq "Y") {
                Write-Host ""
                Write-Host "  Press Enter to accept default; type 's' to skip any field." -ForegroundColor DarkGray
                Write-Host "  API_BASE_URL stays untouched (default is fine)." -ForegroundColor DarkGray

                $configuredCount = 0
                $skippedGroups = @()
                $warnings = @()

                Write-Host ""
                Write-Host "--- Identity ---" -ForegroundColor Cyan
                $defName = Get-EffectiveDefault $existingRaw "USER_NAME" ""
                $userName = Read-EnvInput "Your name" $defName $true
                $resName = Save-OrPreserveEnvKey -FilePath $envFile -Key "USER_NAME" -NewValue $userName
                if ($resName.Configured) { $configuredCount++ }

                Write-Host ""
                Write-Host "--- Fast Brain (MANDATORY) ---" -ForegroundColor Cyan
                $fbKey = Read-EnvInput "Fast Brain API Key (Groq/OpenAI-compatible)" "" $true
                $defFbEnd = Get-EffectiveDefault $existingRaw "FAST_BRAIN_ENDPOINT" "https://api.groq.com/openai/v1"
                $defFbMod = Get-EffectiveDefault $existingRaw "FAST_BRAIN_MODEL" "llama-3.3-70b-versatile"
                $fbEndpoint = Read-EnvInput "Fast Brain Endpoint" $defFbEnd
                $fbModel = Read-EnvInput "Fast Brain Model" $defFbMod
                $resFb = Save-OrPreserveEnvKey -FilePath $envFile -Key "FAST_BRAIN_API_KEY" -NewValue $fbKey -SilentSkip
                if ($resFb.Configured) {
                    $configuredCount++
                    $fbKey = $resFb.EffectiveValue
                } else {
                    Write-Warn "FAST_BRAIN_API_KEY skipped (agent may NOT boot)."
                    $warnings += "FAST_BRAIN_API_KEY not configured"
                }
                Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_ENDPOINT" -Value $fbEndpoint
                Set-EnvValue -FilePath $envFile -Key "FAST_BRAIN_MODEL" -Value $fbModel

                Write-Host ""
                Write-Host "--- Semantic Router ---" -ForegroundColor Cyan
                $defRtrEnd = Get-EffectiveDefault $existingRaw "ROUTER_ENDPOINT" "https://api.groq.com/openai/v1"
                $defRtrMod = Get-EffectiveDefault $existingRaw "ROUTER_MODEL" "llama-3.3-70b-versatile"
                $rtr = Read-KeyWithReuse "Router" $fbKey $fbEndpoint $fbModel $defRtrEnd $defRtrMod
                $resRtr = Save-OrPreserveEnvKey -FilePath $envFile -Key "ROUTER_API_KEY" -NewValue $rtr.Key
                if ($resRtr.Configured) { $configuredCount++ }
                Set-EnvValue -FilePath $envFile -Key "ROUTER_ENDPOINT" -Value $rtr.Endpoint
                Set-EnvValue -FilePath $envFile -Key "ROUTER_MODEL" -Value $rtr.Model

                Write-Host ""
                Write-Host "--- LTM Extraction ---" -ForegroundColor Cyan
                $defLtmEnd = Get-EffectiveDefault $existingRaw "LTM_EXTRACTION_ENDPOINT" "https://api.groq.com/openai/v1"
                $defLtmMod = Get-EffectiveDefault $existingRaw "LTM_EXTRACTION_MODEL" "llama-3.3-70b-versatile"
                $ltm = Read-KeyWithReuse "LTM Extraction" $fbKey $fbEndpoint $fbModel $defLtmEnd $defLtmMod
                $resLtm = Save-OrPreserveEnvKey -FilePath $envFile -Key "LTM_EXTRACTION_API_KEY" -NewValue $ltm.Key
                if ($resLtm.Configured) { $configuredCount++ }
                Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_ENDPOINT" -Value $ltm.Endpoint
                Set-EnvValue -FilePath $envFile -Key "LTM_EXTRACTION_MODEL" -Value $ltm.Model

                Write-Host ""
                Write-Host "--- Proactive Agent ---" -ForegroundColor Cyan
                $defProEnd = Get-EffectiveDefault $existingRaw "PROACTIVE_ENDPOINT" "https://api.groq.com/openai/v1"
                $defProMod = Get-EffectiveDefault $existingRaw "PROACTIVE_MODEL" "llama-3.3-70b-versatile"
                $pro = Read-KeyWithReuse "Proactive" $fbKey $fbEndpoint $fbModel $defProEnd $defProMod
                $resPro = Save-OrPreserveEnvKey -FilePath $envFile -Key "PROACTIVE_API_KEY" -NewValue $pro.Key
                if ($resPro.Configured) { $configuredCount++ }
                Set-EnvValue -FilePath $envFile -Key "PROACTIVE_ENDPOINT" -Value $pro.Endpoint
                Set-EnvValue -FilePath $envFile -Key "PROACTIVE_MODEL" -Value $pro.Model

                Write-Host ""
                Write-Host "--- Agentic Brain: Primary ---" -ForegroundColor Cyan
                $priKey = Read-EnvInput "Primary API Key (OpenAI / any provider)" "" $true
                $defPriBase = Get-EffectiveDefault $existingRaw "PRIMARY_BASE_URL" "https://api.openai.com/v1"
                $defPriMod = Get-EffectiveDefault $existingRaw "PRIMARY_MODEL" "gpt-4o-mini"
                $priBase = Read-EnvInput "Primary Base URL" $defPriBase
                $priModel = Read-EnvInput "Primary Model" $defPriMod
                $priThink = Read-YesNo "Enable thinking for Primary?" "Y"
                $resPri = Save-OrPreserveEnvKey -FilePath $envFile -Key "PRIMARY_API_KEY" -NewValue $priKey
                if ($resPri.Configured) {
                    $configuredCount++
                    $priKey = $resPri.EffectiveValue
                }
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_BASE_URL" -Value $priBase
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_MODEL" -Value $priModel
                Set-EnvValue -FilePath $envFile -Key "PRIMARY_THINKING_ENABLED" -Value $(if ($priThink -eq "Y") { "true" } else { "false" })

                Write-Host ""
                Write-Host "--- Agentic Brain: Fallback ---" -ForegroundColor Cyan
                if (-not [string]::IsNullOrWhiteSpace($priKey) -and (Read-YesNo "Fallback = same as Primary?" "N") -eq "Y") {
                    $fblKey = $priKey; $fblBase = $priBase; $fblModel = $priModel; $fblThink = $priThink
                } else {
                    $fblKey = Read-EnvInput "Fallback API Key" "" $true
                    $defFblBase = Get-EffectiveDefault $existingRaw "FALLBACK_BASE_URL" "https://api.openai.com/v1"
                    $defFblMod = Get-EffectiveDefault $existingRaw "FALLBACK_MODEL" "gpt-4o-mini"
                    $fblBase = Read-EnvInput "Fallback Base URL" $defFblBase
                    $fblModel = Read-EnvInput "Fallback Model" $defFblMod
                    $fblThink = Read-YesNo "Enable thinking for Fallback?" "Y"
                }
                $resFbl = Save-OrPreserveEnvKey -FilePath $envFile -Key "FALLBACK_API_KEY" -NewValue $fblKey
                if ($resFbl.Configured) { $configuredCount++ }
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_BASE_URL" -Value $fblBase
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_MODEL" -Value $fblModel
                Set-EnvValue -FilePath $envFile -Key "FALLBACK_THINKING_ENABLED" -Value $(if ($fblThink -eq "Y") { "true" } else { "false" })

                Write-Host ""
                Write-Host "--- Image Generation (optional) ---" -ForegroundColor Cyan
                if ((Read-YesNo "Configure Image Generation?" "N") -eq "Y") {
                    $imgKey = Read-EnvInput "Image Gen API Key" "" $true
                    $defImgEnd = Get-EffectiveDefault $existingRaw "IMAGE_GEN_ENDPOINT" "https://api.openai.com/v1"
                    $defImgMod = Get-EffectiveDefault $existingRaw "IMAGE_GEN_MODEL" "dall-e-3"
                    $imgEndpoint = Read-EnvInput "Image Gen Endpoint" $defImgEnd
                    $imgModel = Read-EnvInput "Image Gen Model" $defImgMod
                    $resImg = Save-OrPreserveEnvKey -FilePath $envFile -Key "IMAGE_GEN_API_KEY" -NewValue $imgKey
                    if ($resImg.Configured) { $configuredCount++ }
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
                    $resGem = Save-OrPreserveEnvKey -FilePath $envFile -Key "GEMINI_API_KEY" -NewValue $gem
                    if ($resGem.Configured) { $configuredCount++ }
                    $resTav = Save-OrPreserveEnvKey -FilePath $envFile -Key "TAVILY_API_KEY" -NewValue $tav
                    if ($resTav.Configured) { $configuredCount++ }
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
                    $resDg = Save-OrPreserveEnvKey -FilePath $envFile -Key "DEEPGRAM_API_KEY" -NewValue $dg
                    if ($resDg.Configured) { $configuredCount++ }
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
                    $resTtsKey = Save-OrPreserveEnvKey -FilePath $envFile -Key "TTS_API_KEY" -NewValue $ttsKey
                    if ($resTtsKey.Configured) { $configuredCount++ }
                    [void](Save-OrPreserveEnvKey -FilePath $envFile -Key "TTS_ENDPOINT" -NewValue $ttsEndpoint)
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
                    [void](Save-OrPreserveEnvKey -FilePath $envFile -Key "TELEGRAM_API_ID" -NewValue $tgId)
                    [void](Save-OrPreserveEnvKey -FilePath $envFile -Key "TELEGRAM_API_HASH" -NewValue $tgHash)
                    [void](Save-OrPreserveEnvKey -FilePath $envFile -Key "TELEGRAM_BOT_USERNAME" -NewValue $tgBot)
                } else {
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_ID" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_API_HASH" -OnlyIfPlaceholder
                    Clear-EnvValue -FilePath $envFile -Key "TELEGRAM_BOT_USERNAME" -OnlyIfPlaceholder
                    Write-Warn "Telegram skipped."
                    $skippedGroups += "Telegram"
                }

                $envContent = Read-Utf8FileClean -FilePath $envFile
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
            } else {
                Write-Warn "Interactive API key configuration skipped. You can edit $envFile anytime."
            }
        }

        Write-Step "7/7" "Registering Global 'jarvis' CLI Command..."
        $registryScript = Join-Path $installPath "SetupRegistry.py"
        if (Test-Path $registryScript) {
            & $venvPython $registryScript
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "SetupRegistry.py returned a non-zero exit code ($LASTEXITCODE)."
            } else {
                Update-SessionPath
                Broadcast-EnvironmentChange
                Write-Success "Global 'jarvis' CLI command registered via SetupRegistry.py and activated."
            }
        } else {
            Write-Fail "SetupRegistry.py not found in $installPath."
        }

        try {
            $initCommit = (& git rev-parse HEAD 2>$null | Out-String).Trim()
            $initTag = (& git describe --tags --exact-match HEAD 2>$null | Out-String).Trim()
            if (-not $initTag) {
                $initTag = (& git describe --tags --abbrev=0 2>$null | Out-String).Trim()
            }
            $initVersion = if ($initTag) { $initTag } elseif ($initCommit) { $initCommit.Substring(0, [Math]::Min(8, $initCommit.Length)) } else { "v1.0.0" }
            $reqFile = Join-Path $installPath "requirements.txt"
            $depsHash = if (Test-Path $reqFile) { (Get-FileHash -Path $reqFile -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
            $npmCombined = ""
            $pkgJson = Join-Path $baileysPath "package.json"
            $pkgLock = Join-Path $baileysPath "package-lock.json"
            if (Test-Path $pkgJson) { $npmCombined += (Get-FileHash -Path $pkgJson -Algorithm SHA256).Hash }
            if (Test-Path $pkgLock) { $npmCombined += (Get-FileHash -Path $pkgLock -Algorithm SHA256).Hash }
            $npmHash = ""
            if ($npmCombined) {
                $sha = [System.Security.Cryptography.SHA256]::Create()
                try {
                    $hb = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($npmCombined))
                    $npmHash = -join ($hb | ForEach-Object { $_.ToString("x2") })
                } finally { $sha.Dispose() }
            }
            $stateObj = [pscustomobject]@{
                channel                       = "stable"
                version                       = $initVersion
                commit                        = $initCommit
                previous_version              = ""
                previous_commit               = ""
                previous_channel              = ""
                last_backup_path              = ""
                deps_hash                     = $depsHash
                npm_hash                      = $npmHash
                last_edge_prompt_at           = $null
                edge_prompt_snooze_until      = $null
                edge_prompt_dismissed_count   = 0
                edge_prompt_permanently_muted = $false
                last_rollback_at              = $null
                last_updated_at               = (Get-Date).ToUniversalTime().ToString("o")
            }
            Write-Utf8NoBom -FilePath (Join-Path $installPath ".jarvis_state.json") -Content ($stateObj | ConvertTo-Json -Depth 10)
        } catch {}

        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "      J.A.R.V.I.S. OS Agent Installed Successfully!       " -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "  Install Location : $installPath" -ForegroundColor White
        Write-Host "  Config File      : $envFile" -ForegroundColor White
        Write-Host "  Launch Command   : jarvis" -ForegroundColor Cyan
        if ($vcRebootRequired) {
            Write-Host "  Notice           : Please restart Windows once to finalize VC++ runtime." -ForegroundColor Yellow
        }
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host ""
    } finally {
        Pop-Location
    }
}

Install-Jarvis