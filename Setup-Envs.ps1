[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Merge
)

$ErrorActionPreference = "Stop"
Write-Host "Initializing local environment files..." -ForegroundColor Cyan

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition

$envFiles = @(
    @{ Source = ".env.template"; Target = "backend/.env"; Name = "Docker Root" },
    @{ Source = ".env.template"; Target = "backend/api/.env"; Name = "FastAPI Backend" },
    @{ Source = ".env.template"; Target = "simulation/.env"; Name = "Hardware Simulation" }
)

foreach ($file in $envFiles) {
    $src = Join-Path -Path $ProjectRoot -ChildPath $file.Source
    $tgt = Join-Path -Path $ProjectRoot -ChildPath $file.Target

    if (-not (Test-Path -Path $src)) {
        Write-Warning "Master template '$($file.Source)' not found!"
        continue
    }

    if (-not (Test-Path -Path $tgt)) {
        Copy-Item -Path $src -Destination $tgt
        Write-Host "Created $($file.Name) (.env) from template." -ForegroundColor Green
        continue
    }

    if ($Force) {
        Copy-Item -Path $src -Destination $tgt -Force
        Write-Host "Overwritten $($file.Name) (.env) with template (-Force)." -ForegroundColor Yellow
        continue
    }

    if ($Merge) {
        Write-Host "Merging new keys into $($file.Name) (.env)..." -ForegroundColor Cyan
        $existingKeys = @{}
        
        Get-Content -Path $tgt | Where-Object { $_ -match '^[^#]+=' } | ForEach-Object {
            $parts = $_ -split '=', 2
            $existingKeys[$parts[0].Trim()] = $parts[1].Trim()
        }

        $appendedCount = 0
        $sourceLines = Get-Content -Path $src
        foreach ($line in $sourceLines) {
            if ($line -match '^[^#]+=') {
                $parts = $line -split '=', 2
                $key = $parts[0].Trim()
                if (-not $existingKeys.ContainsKey($key)) {
                    Add-Content -Path $tgt -Value $line
                    Write-Host " + Added missing key: $key" -ForegroundColor Gray
                    $appendedCount++
                }
            }
        }
        
        if ($appendedCount -eq 0) {
            Write-Host " - Already up to date." -ForegroundColor DarkGray
        }
        continue
    }

    Write-Host "File $($file.Name) (.env) already exists. Skipping. Use -Merge to update or -Force to overwrite." -ForegroundColor DarkGray
}

Write-Host "Environment setup complete." -ForegroundColor Green