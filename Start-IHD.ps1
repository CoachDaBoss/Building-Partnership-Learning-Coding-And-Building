$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "data\ihd.sqlite3")) {
    Write-Host "IT HIT DIFFERENT LLC - First Boot" -ForegroundColor Yellow
    $masterEmail = Read-Host "Master owner email"
    $masterName = Read-Host "Master owner display name (example: CoachDaBoss)"
    $secure = Read-Host "Create master password (12+ characters)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ($plain.Length -lt 12) { throw "Master password must be at least 12 characters." }
    $env:IHD_MASTER_EMAIL = $masterEmail
    $env:IHD_MASTER_NAME = $masterName
    $env:IHD_MASTER_PASSWORD = $plain
}

Write-Host "Starting IT HIT DIFFERENT LLC Creator Network..." -ForegroundColor Green
Write-Host "Opening http://127.0.0.1:8787 in your browser..." -ForegroundColor Cyan
Start-Process "http://127.0.0.1:8787"
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.11 server.py
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python server.py
} else {
    Write-Host "Python 3.11 is not available. Install it or add it to PATH." -ForegroundColor Red
    exit 1
}
