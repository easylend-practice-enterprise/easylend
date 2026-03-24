# ENV setup

## Purpose

- Centralize local environment variables and provide a safe onboarding script.

## Files

- `.env.template` (repo root): canonical, commented template. Edit this to add or document variables.
- `.env` files: local runtime files (gitignored).

## Usage

- Create/update local `.env` files from the master template:

  - Merge missing keys (preserve your local values):

    ```powershell
    .\Setup-Envs.ps1 -Merge
    ```

  - Overwrite targets with the template (destructive):

    ```powershell
    .\Setup-Envs.ps1 -Force
    ```

## Behavior

- The script maps keys from `.env.template` into service-specific `.env` targets.
- `-Merge` appends missing keys only.
- `-Force` recreates/overwrites the target files from the template.
- After syncing, the script validates a small set of required keys and exits non-zero if any are missing.

## Security

- Do NOT commit real secrets. Keep `.env` files gitignored and use secure secret storage for production.
