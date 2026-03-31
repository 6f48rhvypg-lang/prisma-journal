# PrismA - Secure Journal App - Startup Script
# Run with: .\start.ps1 or double-click start.bat

$ErrorActionPreference = "SilentlyContinue"
$Host.UI.RawUI.WindowTitle = "PrismA - Secure Journal"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PrismA - Secure Journal - Starting Up..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
Set-Location $PSScriptRoot

# --- Find best Python version ---
Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow

# Prefer Python 3.11 or 3.12 for ML package compatibility
$pythonCmd = $null
$pythonVer = $null

# Check for py launcher with specific versions first
$pyVersions = @("3.12", "3.11", "3.13", "3.10")
foreach ($ver in $pyVersions) {
    $result = py -$ver --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "py -$ver"
        $pythonVer = $ver
        break
    }
}

# Fall back to default python
if (-not $pythonCmd) {
    $result = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "python"
        $pythonVer = ($result -replace "Python ", "").Trim()
    }
}

if (-not $pythonCmd) {
    Write-Host "      Python not found! Install from python.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "      Using Python $pythonVer" -ForegroundColor Green

# Check if version is too new for ML packages
$majorMinor = ($pythonVer -split '\.')[0..1] -join '.'
$needsWarning = $false
try {
    if ([double]$majorMinor -ge 3.13) { $needsWarning = $true }
} catch {}

if ($needsWarning) {
    Write-Host ""
    Write-Host "      WARNING: Python $pythonVer is very new" -ForegroundColor Yellow
    Write-Host "      ML packages may not install. App will work with core features." -ForegroundColor DarkYellow
    Write-Host "      For full features, install Python 3.11 or 3.12" -ForegroundColor DarkYellow
    Write-Host ""
}

# --- Virtual Environment ---
Write-Host "[2/4] Setting up environment..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\python.exe") {
    & .\venv\Scripts\Activate.ps1
    Write-Host "      Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "      Creating virtual environment..." -ForegroundColor Yellow
    Invoke-Expression "$pythonCmd -m venv venv"
    & .\venv\Scripts\Activate.ps1
    Write-Host "      Virtual environment created" -ForegroundColor Green
}

# --- Dependencies ---
Write-Host "[3/4] Installing packages..." -ForegroundColor Yellow

# Core packages (always work)
$hasFlask = python -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Core packages..." -ForegroundColor Gray
    pip install flask flask-cors flask-compress python-dotenv requests psutil --quiet 2>$null
}

# Skip ML packages on Python 3.13+ (they won't install without build tools)
if (-not $needsWarning) {
    # ML packages - only try on supported Python versions
    $mlPackages = @(
        @{name="numpy"; import="numpy"; desc="math"},
        @{name="chromadb"; import="chromadb"; desc="search"},
        @{name="sentence-transformers"; import="sentence_transformers"; desc="embeddings"},
        @{name="openai-whisper"; import="whisper"; desc="voice"}
    )

    foreach ($pkg in $mlPackages) {
        $installed = python -c "import $($pkg.import)" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "      $($pkg.desc)..." -ForegroundColor Gray
            # Use timeout to prevent hanging on build attempts
            $job = Start-Job -ScriptBlock {
                param($pkgName)
                pip install $pkgName --quiet 2>$null
            } -ArgumentList $pkg.name

            $completed = Wait-Job $job -Timeout 60
            if (-not $completed) {
                Stop-Job $job
                Write-Host "      $($pkg.name) skipped (timeout)" -ForegroundColor DarkYellow
            }
            Remove-Job $job -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "      Skipping ML packages (Python too new)" -ForegroundColor DarkYellow
}

Write-Host "      Done" -ForegroundColor Green

# --- Ollama ---
Write-Host "[4/5] Checking Ollama..." -ForegroundColor Yellow
$ollamaRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        $ollamaRunning = $true
    }
} catch {}

if ($ollamaRunning) {
    Write-Host "      Ollama running" -ForegroundColor Green
} else {
    # Try to find Ollama in common Windows locations
    $ollamaExe = $null
    $possiblePaths = @(
        "ollama",
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Ollama\ollama.exe"
    )
    
    foreach ($path in $possiblePaths) {
        if ($path -eq "ollama") {
            $cmd = Get-Command ollama -ErrorAction SilentlyContinue
            if ($cmd) {
                $ollamaExe = $cmd.Source
                break
            }
        } elseif (Test-Path $path) {
            $ollamaExe = $path
            break
        }
    }
    
    if ($ollamaExe) {
        Write-Host "      Starting Ollama..." -ForegroundColor Yellow
        # Start Ollama in the background
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        
        # Also try to open the Ollama app window (if available)
        $ollamaAppPath = "$env:LOCALAPPDATA\Programs\Ollama\Ollama.exe"
        if (Test-Path $ollamaAppPath) {
            Start-Process -FilePath $ollamaAppPath
        }

        $attempts = 0
        while ($attempts -lt 15) {
            Start-Sleep -Seconds 1
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 1 -UseBasicParsing
                if ($response.StatusCode -eq 200) {
                    Write-Host "      Ollama started" -ForegroundColor Green
                    break
                }
            } catch {}
            $attempts++
            if ($attempts -eq 10) {
                Write-Host "      Still waiting for Ollama..." -ForegroundColor DarkYellow
            }
        }
        
        if ($attempts -ge 15) {
            Write-Host "      Ollama may need manual start - check system tray" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "      Ollama not found - install from ollama.ai" -ForegroundColor DarkYellow
    }
}

# --- ComfyUI ---
Write-Host "[5/5] Checking ComfyUI..." -ForegroundColor Yellow
$comfyRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8188" -TimeoutSec 2 -UseBasicParsing
    if ($response.StatusCode -eq 200) { $comfyRunning = $true }
} catch {}

if ($comfyRunning) {
    Write-Host "      ComfyUI already running" -ForegroundColor Green
} else {
    # Common ComfyUI install locations
    $comfyPaths = @(
        "C:\ComfyUI",
        "$env:USERPROFILE\ComfyUI",
        "$env:USERPROFILE\Desktop\ComfyUI",
        "D:\ComfyUI"
    )

    $comfyDir = $null
    foreach ($path in $comfyPaths) {
        if (Test-Path "$path\main.py") {
            $comfyDir = $path
            break
        }
    }

    if ($comfyDir) {
        Write-Host "      Starting ComfyUI from $comfyDir..." -ForegroundColor Yellow
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c cd /d `"$comfyDir`" && python main.py --listen --port 8188" -WindowStyle Minimized
        Write-Host "      ComfyUI starting in background (http://127.0.0.1:8188)" -ForegroundColor Green
    } else {
        Write-Host "      ComfyUI not found - image generation will use cloud API or be unavailable" -ForegroundColor DarkYellow
        Write-Host "      Install ComfyUI to one of: C:\ComfyUI, $env:USERPROFILE\ComfyUI" -ForegroundColor DarkGray
    }
}

# --- Start Flask App ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   http://localhost:5000" -ForegroundColor Green
Write-Host "   Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   Tip: Use --ollama or --lmstudio to override LLM provider" -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Open browser
Start-Job -ScriptBlock { Start-Sleep 2; Start-Process "http://localhost:5000" } | Out-Null

# Run Flask (pass through any command-line arguments)
python app/app.py $args
