# Development Workflow & Contributing

This repository operates as a Monorepo. To ensure code quality and traceability in a team environment, we follow the rules in this contribution guide. Direct pushes to `main` are blocked via GitHub Rulesets; all changes go through branches and Pull Requests.

**Key points:**

- Branches must reference YouTrack issues (`ELP-<id>`).
- Follow the Conventional Commits specification.
- Use Pull Requests with `Squash and Merge`.

## 1. Branching Strategy & YouTrack Flow

1. Claim an issue in YouTrack (e.g. `ELP-14`).
2. Create a local branch with the type and YouTrack ID: `type/ELP-<id>-short-description`.

- Examples: `feat/ELP-14-setup-fastapi`, `fix/ELP-74-camera-crash`.

1. Work locally, push to the remote branch, and open a Pull Request towards `main`.
2. After a successful review and CI, the PR is merged with `Squash and Merge` and the feature branch is deleted.

Branch type conventions:

- `feat/`: new functionality
- `fix/`: bug fixes
- `docs/`: documentation
- `chore/`, `refactor/`, `test/` as appropriate

## 2. Commit Message Conventions

We follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/). This makes the git history machine-parseable and consistent.

Required format for commits and PR titles:

`type(scope): ELP-<id> short description`

- `type`: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- `scope`: component (e.g. `api`, `kiosk`, `auth`, `infra`)
- `ELP-<id>`: YouTrack issue ID (REQUIRED)

Examples:

- `feat(auth): ELP-26 add jwt login endpoint`
- `fix(camera): ELP-74 fix crash on startup`
- `docs(readme): ELP-66 update installation steps`
- `chore(docker): ELP-16 update postgres version`

IMPORTANT: Because we use `Squash and Merge`, the PR title becomes the final commit message. Make sure your PR title follows this format.

## 3. Pull Request Workflow

1. Push your feature branch to the remote.
2. Open a Pull Request to `main` with the correct title (Conventional Commit + ELP-ID).
3. Ensure all CI/CD checks are green (tests, lint, build).
4. Request at least one team member for review and obtain approval.
5. Merge via `Squash and Merge` and delete the feature branch.

Practical tips:

- Add a short summary, test instructions, and relevant YouTrack links to the PR description.

## 4. Cross-Platform Git / Line Endings

The team develops on both Windows and Linux; our servers (Docker/Ubuntu) use Linux. To prevent CRLF/LF issues and "bad interpreter" errors in containers, we enforce a `gitattributes` policy.

Note: If you need help, a `.gitattributes` file can be added to the repository.

## 5. Additional rules and recommendations

- Always include the relevant `ELP-<id>` in commits and PR titles so that automation and traceability work correctly.
- Remove feature branches after merging to keep the branch list clean.
- Follow team conventions for scope names (e.g. `api`, `kiosk`, `infra`, `auth`).

---
A `.gitattributes` file can be added and/or `docs/workflow.md` updated with a reference to this contribution guide if needed.

## 6. Recommended local `git config` settings

To ensure consistent behaviour across developers, we recommend the following local/global `git` settings. Always add `ELP-<id>` to commits and PR titles as described above.

Windows (example from a developer):

```powershell
PS C:\Users\User> git config --global --list
core.editor="C:\Users\User\AppData\Local\Programs\Microsoft VS Code\bin\code" --wait
core.autocrlf=true
core.safecrlf=false
pull.rebase=false
user.name=Username
user.email=email@example.com
init.defaultbranch=main
fetch.prune=true
PS C:\Users\User>
```

To apply these settings on Windows, use the following commands in PowerShell:

```powershell
git config --global core.editor "C:\Users\User\AppData\Local\Programs\Microsoft VS Code\bin\code --wait"
git config --global core.autocrlf true
git config --global core.safecrlf false
git config --global pull.rebase false
git config --global user.name "Username"
git config --global user.email "email@example.com"
git config --global init.defaultbranch main
git config --global fetch.prune true
```

Linux/macOS (recommended variant: adjust paths and preferences):

On Linux we recommend setting `core.autocrlf` to `input` (convert CRLF → LF on commit) or `false` if you fully trust `.gitattributes`. An example config:

```bash
git config --global --list
core.editor=code --wait
core.autocrlf=input
core.safecrlf=true
pull.rebase=false
user.name=Username
user.email=email@example.com
init.defaultbranch=main
fetch.prune=true
```

And the corresponding commands:

```bash
git config --global core.editor "code --wait"
git config --global core.autocrlf input
git config --global core.safecrlf true
git config --global pull.rebase false
git config --global user.name "Username"
git config --global user.email "email@example.com"
git config --global init.defaultbranch main
git config --global fetch.prune true
```

Note:

- We keep `.gitattributes` in the repo as the primary source of truth for end-of-line normalisation. These `git config` recommendations are intended to give developers a consistent, safe local setup.
- A short `setup` script or README addition can be provided if needed.

## 7. Bug Fixes After a Squash & Merge

Have you successfully squashed and merged a branch (e.g. `ELP-16`), but later discover a bug?
**Never reopen the old branch and never force-push over history.**

Always follow this enterprise flow:

1. Move the original ticket in YouTrack back to "In Progress" (or create a new bug ticket).
2. Make sure you are on the latest `main` branch locally (`git pull origin main`).
3. Create a **new** fix branch from `main` (e.g. `fix/ELP-16-database-url-typo`).
4. Fix the code, push the new branch, and open a fresh Squash & Merge PR.
This keeps the `main` timeline always moving forward without Git conflicts.
