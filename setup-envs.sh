#!/bin/bash

set -e

FORCE=false
MERGE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--force) FORCE=true ;;
    -m|--merge) MERGE=true ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
  shift
done

echo "Initializing local environment files from master template..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_TEMPLATE="$PROJECT_ROOT/.env.template"

if [[ ! -f "$MASTER_TEMPLATE" ]]; then
  echo "ERROR: Master template not found at $MASTER_TEMPLATE"
  exit 1
fi

# Define the exact routing mapping: which keys belong to which file
# Name, Target, AllowedKeys (space-separated), RequiredKeys (space-separated)
declare -a MAPPINGS=(
  "Docker Root|backend/.env|POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REDIS_PASSWORD PGADMIN_DEFAULT_EMAIL PGADMIN_DEFAULT_PASSWORD SQLBAK_TOKEN GHCR_USERNAME GHCR_PAT NTFY_WEBHOOK_URL|POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REDIS_PASSWORD"
  "FastAPI Backend|backend/api/.env|ENVIRONMENT JWT_SECRET_KEY DATABASE_URL REDIS_URL VISION_BOX_API_KEY SIMULATION_API_KEY VISION_SERVICE_URL SIMULATION_SERVICE_URL VISION_API_KEY DOCS_USERNAME DOCS_PASSWORD|ENVIRONMENT JWT_SECRET_KEY DATABASE_URL REDIS_URL VISION_BOX_API_KEY SIMULATION_API_KEY VISION_API_KEY"
  "Hardware Simulation|simulation/.env|VISIONBOX_WS_URL SIMULATION_API_KEY|VISIONBOX_WS_URL SIMULATION_API_KEY"
)

# Parse the master template into an associative array
declare -A MASTER_KEYS
while IFS='=' read -r key value; do
  # Skip comments and empty lines
  [[ -z "$key" || "$key" =~ ^# ]] && continue
  MASTER_KEYS["$key"]="$value"
done < "$MASTER_TEMPLATE"

ENV_VALIDATION_FAILED=false

for mapping in "${MAPPINGS[@]}"; do
  IFS='|' read -r name target allowed_keys required_keys <<< "$mapping"
  tgt_path="$PROJECT_ROOT/$target"

  if [[ ! -f "$tgt_path" ]] || [[ "$FORCE" == true ]]; then
    touch "$tgt_path"
    echo "Created/Overwritten $name at $target"
  elif [[ "$MERGE" != true ]]; then
    echo "Skipping $target (already exists). Use -m/--merge or -f/--force."
    continue
  fi

  echo "Syncing keys for $name..."

  # Read existing target keys into associative array
  declare -A EXISTING_KEYS
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    EXISTING_KEYS["$key"]="$value"
  done < "$tgt_path"

  # Inject only the allowed keys that are missing
  appended_count=0
  for key in $allowed_keys; do
    if [[ -n "${MASTER_KEYS[$key]}" ]] && [[ -z "${EXISTING_KEYS[$key]}" ]]; then
      echo "$key=${MASTER_KEYS[$key]}" >> "$tgt_path"
      echo "  + Added key: $key"
      ((appended_count++))
    fi
  done

  if [[ $appended_count -eq 0 ]]; then
    echo "  - Already up to date."
  fi

  # Validation: ensure required keys are present in the target
  declare -A FINAL_KEYS
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    FINAL_KEYS["$key"]="$value"
  done < "$tgt_path"

  missing=""
  for req in $required_keys; do
    [[ -z "${FINAL_KEYS[$req]}" ]] && missing="$missing $req"
  done

  if [[ -n "$missing" ]]; then
    echo "  !! Missing required keys for $name:$missing" >&2
    ENV_VALIDATION_FAILED=true
  fi
done

if [[ "$ENV_VALIDATION_FAILED" == true ]]; then
  echo "ERROR: One or more required environment keys are missing. Please update the target .env files or the .env.template and re-run with -m/--merge or -f/--force." >&2
  exit 1
fi

echo "Environment setup complete."