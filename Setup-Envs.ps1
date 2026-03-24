[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "Initializing local environment files..."

# Resolve script root so the script works when invoked from any cwd
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition

$envFiles = @(
    @{ Source = "backend/.env.example"; Target = "backend/.env" },
    @{ Source = "backend/api/.env.example"; Target = "backend/api/.env" },
    @{ Source = "simulation/.env.example"; Target = "simulation/.env" }
)

foreach ($file in $envFiles) {
    $src = Join-Path $ScriptRoot $file.Source
    $tgt = Join-Path $ScriptRoot $file.Target

    if (Test-Path $src) {
        if ((-not (Test-Path $tgt)) -or $Force) {
            Copy-Item -Path $src -Destination $tgt -Force:$Force
            Write-Host "Created/Updated $($file.Target) from template."
        }
        else {
            Write-Host "File $($file.Target) already exists. Skipping. Use -Force to overwrite."
        }
    }
    else {
        Write-Host "Warning: Template $($file.Source) not found." -ForegroundColor Yellow
    }
}

Write-Host "Environment setup complete."