# Development Workflow & Contributing

Dit repository opereert als een Monorepo. Om code-kwaliteit en traceerbaarheid in een teamomgeving te waarborgen, volgen we de regels in deze bijdragehandleiding. Direct pushen naar `main` is geblokkeerd via GitHub Rulesets; alle wijzigingen verlopen via branches en Pull Requests.

**Kernpunten:**

- Branches moeten YouTrack-issues refereren (`ELP-<id>`).
- Volg de Conventional Commits specificatie.
- Gebruik Pull Requests en `Squash and Merge`.

## 1. Branching Strategy & YouTrack Flow

1. Claim een issue in YouTrack (bijv. `ELP-14`).
2. Maak een lokale branch met het type en YouTrack-ID: `type/ELP-<id>-korte-beschrijving`.

- Voorbeelden: `feat/ELP-14-setup-fastapi`, `fix/ELP-74-camera-crash`.

1. Werk lokaal, push naar de remote branch en open een Pull Request naar `main`.
2. Na succesvolle review en CI wordt de PR samengevoegd met `Squash and Merge` en de feature-branch verwijderd.

Branch type conventies:

- `feat/`: nieuwe functionaliteit
- `fix/`: bugfixes
- `docs/`: documentatie
- `chore/`, `refactor/`, `test/` zoals passend

## 2. Commit Message Conventies

We volgen [Conventional Commits 1.0.0](https://www.conventionalcommits.org/). Dit maakt de git-history machine-parseable en consistent.

Verplicht formaat for commits and PR-titels:

`type(scope): ELP-<id> korte beschrijving`

- `type`: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- `scope`: onderdeel (bv. `api`, `kiosk`, `auth`, `infra`)
- `ELP-<id>`: YouTrack issue-ID (VERPLICHT)

Voorbeelden:

- `feat(auth): ELP-26 add jwt login endpoint`
- `fix(camera): ELP-74 fix crash on startup`
- `docs(readme): ELP-66 update installation steps`
- `chore(docker): ELP-16 update postgres version`

BELANGRIJK: Omdat we `Squash and Merge` gebruiken, wordt de PR-titel de uiteindelijke commit message. Zorg dat je PR-titel dit formaat volgt.

## 3. Pull Request Workflow

1. Push je feature-branch naar de remote.
2. Open een Pull Request naar `main` met de correcte titel (Conventional Commit + ELP-ID).
3. Zorg dat alle CI/CD checks groen zijn (tests, lint, build).
4. Vraag minimaal één teamlid om review en verkrijg goedkeuring.
5. Merge via `Squash and Merge` en verwijder de feature-branch.

Praktische tips:

- Voeg in de PR-omschrijving een korte samenvatting, testinstructies en relevante YouTrack-links toe.

## 4. Cross-Platform Git / Line Endings

Het team ontwikkelt op zowel Windows als Linux, onze servers (Docker/Ubuntu) gebruiken Linux. Om CRLF/LF-problemen en "bad interpreter" fouten in containers te voorkomen, hanteren we een `gitattributes` policy.

Opmerking: Als je hulp wilt, kan ik een `.gitattributes` bestand toevoegen aan de repository.

## 5. Overige regels en aanbevelingen

- Voeg altijd het relevante `ELP-<id>` in commits en PR-titels zodat automatisering en traceerbaarheid werkt.
- Verwijder feature-branches na merge om de branchlijst schoon te houden.
- Volg team conventions voor scope-namen (bv. `api`, `kiosk`, `infra`, `auth`).

---
Als je wilt, voeg ik nu direct een `.gitattributes` bestand toe en/of update de `docs/workflow.md` met een verwijzing naar deze bijdragehandleiding.

## 6. Aanbevolen lokale `git config` instellingen

Om consistente gedrag tussen ontwikkelaars te garanderen, adviseren we de volgende lokale/global `git` instellingen. Voeg altijd `ELP-<id>` toe aan commits en PR-titels zoals eerder beschreven.

Windows (voorbeeld van de ontwikkelaar):

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

Als je deze instellingen wilt toepassen op Windows, gebruik de volgende commando's in PowerShell:

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

Linux/macOS (aanbevolen variant — pas paden en voorkeuren aan):

Op Linux raden we aan `core.autocrlf` op `input` te zetten (convert CRLF → LF on commit) of `false` als je volledig vertrouwt op `.gitattributes`. Een voorbeeldconfig:

```bash
core.editor=code --wait
core.autocrlf=input
core.safecrlf=true
pull.rebase=false
user.name=Username
user.email=email@example.com
init.defaultbranch=main
fetch.prune=true
```

En de bijbehorende commando's:

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

Opmerking:

- Wij behouden `.gitattributes` in de repo als de primaire bron van waarheid voor eol-normalisatie. Deze `git config`-aanbevelingen zijn bedoeld om ontwikkelaars een consistente, veilige lokale setup te geven.
- Als je wilt dat ik deze exacte instellingen in een korte `setup`-script of README toevoeg, dan maak ik dat aan.

## 7. Bugfixes na een Squash & Merge

Heb je een branch succesvol gesquashed en gemerged (bijv. `ELP-16`), maar ontdek je later toch een bug?
**Heropen NOOIT de oude branch en force-push NOOIT over de historie heen.**

Volg altijd deze Enterprise-flow:

1. Sleep het originele ticket in YouTrack terug naar "In Progress" (of maak een nieuw bug-ticket aan).
2. Zorg dat je lokaal op de nieuwste `main` branch zit (`git pull origin main`).
3. Maak een **nieuwe** fix-branch aan vanaf `main` (bijv. `fix/ELP-16-database-url-typo`).
4. Fix de code, push de nieuwe branch, en doe een verse Squash & Merge PR.
Zo blijft de `main` tijdlijn altijd vooruit bewegen zonder Git-conflicten.
