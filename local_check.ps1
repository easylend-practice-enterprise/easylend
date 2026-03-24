param (
    [Parameter(Mandatory = $true, HelpMessage = "Choose 'api' or 'vision'")]
    [ValidateSet("api", "vision")]
    [string]$Target
)

# 1. Check whether Docker is running
Write-Host "Checking whether Docker Desktop is running..." -ForegroundColor Cyan
docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running or not reachable. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# 2. Start the build
Write-Host "Starting local Docker build for $Target..." -ForegroundColor Cyan
docker build -t easylend-$Target-local -f ./backend/$Target/Dockerfile ./backend/$Target

if ($LASTEXITCODE -eq 0) {
    Write-Host "Docker build succeeded!" -ForegroundColor Green
    Write-Host "Starting Grype security scan..." -ForegroundColor Cyan

    # Run Grype scan with the local image and the provided config
    grype easylend-$Target-local -c .grype.yaml --only-fixed

    Write-Host "Done! If the output above looks clean, it's safe to push." -ForegroundColor Green
}
else {
    Write-Host "Docker build failed! Check the errors above and fix your Dockerfile." -ForegroundColor Red
    exit 1
}