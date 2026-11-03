# AVI v0.3.4 one-click bootstrap: only uses official winget sources.
# No user-level environment variable or global Python packages are modified.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$bootstrapLog = Join-Path $logDir 'bootstrap_latest.log'
Set-Content -LiteralPath $bootstrapLog -Value '=== AVI ONE-CLICK BOOTSTRAP ===' -Encoding UTF8
function Say([string] $message) {
    Write-Host $message
    Add-Content -LiteralPath $bootstrapLog -Value $message -Encoding UTF8
}
function Test-Python([string] $file, [string[]] $prefix) {
    try {
        & $file @prefix -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,12) and sys.maxsize>2**32' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
function Find-Python {
    $candidates = @(
        @{ file='py.exe'; prefix=@('-3.12') },
        @{ file='py.exe'; prefix=@('-3.11') },
        @{ file=(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'); prefix=@() },
        @{ file=(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'); prefix=@() },
        @{ file='python.exe'; prefix=@() }
    )
    foreach ($item in $candidates) {
        if (Test-Python $item.file $item.prefix) { return $item }
    }
    return $null
}
try {
    $venvPy = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPy)) {
        $candidate = Find-Python
        if ($null -eq $candidate) {
            Say '[Python] Python 3.11/3.12 64-bit missing. Trying Windows Package Manager...'
            if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
                throw 'Missing Python and winget. Install Python 3.11 x64 from python.org, then rerun this BAT.'
            }
            & winget.exe install --id Python.Python.3.11 --exact --source winget --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) { throw ('winget Python install failed: ' + $LASTEXITCODE) }
            $candidate = Find-Python
            if ($null -eq $candidate) {
                throw 'Python installation returned success but interpreter not located. Reopen CMD or install Python 3.11 x64 manually.'
            }
        }
        Say ('[Python] Creating local .venv using: ' + $candidate.file)
        $cmd = [string]$candidate.file
        $pythonArgs = [string[]]@($candidate.prefix)
        & $cmd @pythonArgs -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    if (-not (Test-Path -LiteralPath $venvPy)) { throw 'Missing .venv\Scripts\python.exe after creation.' }
    Say ('[Python] Local environment: ' + $venvPy)
    & $venvPy (Join-Path $root 'setup_all.py')
    if ($LASTEXITCODE -ne 0) { throw ('setup_all.py failed (exit ' + $LASTEXITCODE + '). Check logs\setup_all_latest.log') }
    Say '[SUCCESS] All requested dependency installation steps finished.'
    exit 0
} catch {
    Say ('[ERROR] ' + $_.Exception.Message)
    exit 1
}
