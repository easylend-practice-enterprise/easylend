[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Merge
)

$ErrorActionPreference = "Stop"
Write-Host "Initializing local environment files from master template..."

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$MasterTemplate = Join-Path -Path $ProjectRoot -ChildPath ".env.template"

if (-not (Test-Path -Path $MasterTemplate)) {
    Write-Error "Master template not found at $MasterTemplate"
    exit 1
}

# Define the exact routing mapping: which keys belong to which file
$EnvMappings = @(
    @{
        Name        = "Docker Root"
        Target      = "backend/.env"
        AllowedKeys = @(
            "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", 
            "REDIS_PASSWORD", "PGADMIN_DEFAULT_EMAIL", "PGADMIN_DEFAULT_PASSWORD", 
            "SQLBAK_TOKEN", "GHCR_USERNAME", "GHCR_PAT", "NTFY_WEBHOOK_URL"
        )
    },
    @{
        Name        = "FastAPI Backend"
        Target      = "backend/api/.env"
        AllowedKeys = @(
            "ENVIRONMENT", "JWT_SECRET_KEY", "DATABASE_URL", "REDIS_URL", 
            "VISION_BOX_API_KEY", "SIMULATION_API_KEY", 
            "VISION_SERVICE_URL", "SIMULATION_SERVICE_URL"
        )
    },
    @{
        Name        = "Hardware Simulation"
        Target      = "simulation/.env"
        AllowedKeys = @(
            "VISIONBOX_WS_URL", "SIMULATION_API_KEY"
        )
    }
)

# Parse the master template into a hashtable
$MasterKeys = @{}
Get-Content -Path $MasterTemplate | Where-Object { $_ -match '^[^#]+=' } | ForEach-Object {
    $parts = $_ -split '=', 2
    $MasterKeys[$parts[0].Trim()] = $parts[1].Trim()
}

foreach ($mapping in $EnvMappings) {
    $tgtPath = Join-Path -Path $ProjectRoot -ChildPath $mapping.Target

    if ((-not (Test-Path -Path $tgtPath)) -or $Force) {
        $null = New-Item -Path $tgtPath -ItemType File -Force
        Write-Host "Created/Overwritten $($mapping.Name) at $($mapping.Target)"
    }
    elseif (-not $Merge) {
        Write-Host "Skipping $($mapping.Target) (already exists). Use -Merge or -Force."
        continue
    }

    Write-Host "Syncing keys for $($mapping.Name)..."
    
    # Read existing target keys
    $existingKeys = @{}
    Get-Content -Path $tgtPath | Where-Object { $_ -match '^[^#]+=' } | ForEach-Object {
        $parts = $_ -split '=', 2
        $existingKeys[$parts[0].Trim()] = $parts[1].Trim()
    }

    # Inject only the allowed keys that are missing
    $appendedCount = 0
    foreach ($key in $mapping.AllowedKeys) {
        if ($MasterKeys.ContainsKey($key) -and -not $existingKeys.ContainsKey($key)) {
            $line = "{0}={1}" -f $key, $MasterKeys[$key]
            Add-Content -Path $tgtPath -Value $line
            Write-Host "  + Added key: $key"
            $appendedCount++
        }
    }

    if ($appendedCount -eq 0) {
        Write-Host "  - Already up to date."
    }
}

Write-Host "Environment setup complete."