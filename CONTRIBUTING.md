# Development Workflow EasyLend

Om de kwaliteit en traceerbaarheid te garanderen, werken we volgens strikte regels.
Direct committen naar `main` is geblokkeerd via GitHub Rulesets.

## 1. Branching Strategy

Wijzigingen gebeuren nooit rechtstreeks op `main`.
Maak voor elke issue in YouTrack een nieuwe Git branch aan:

* `feat/ELP-<id>-korte-beschrijving` (voor nieuwe functionaliteit)
* `fix/ELP-<id>-korte-beschrijving` (voor bugfixes)
* `docs/ELP-<id>-korte-beschrijving` (voor documentatie)

## 2. Commit & PR Conventies

Wij volgen de [Conventional Commits 1.0.0](https://www.conventionalcommits.org/) specificatie.
Dit maakt onze geschiedenis leesbaar en machine-parseable.

Het Formaat:
`type(scope): ELP-<id> beschrijving`

* type: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
* scope: Het onderdeel van de app (bv. `api`, `kiosk`, `auth`, `hardware`).
* `ELP-<id>`: Het YouTrack Issue nummer (VERPLICHT voor koppeling).

Voorbeelden:

* `feat(auth): ELP-26 add jwt login endpoint`
* `fix(camera): ELP-74 fix crash on startup`
* `docs(readme): ELP-66 update installation steps`
* `chore(docker): ELP-16 update postgres version`

BELANGRIJK: Omdat wij Squash Mergen, wordt de titel van je Pull Request uiteindelijk de commit message. Zorg dus dat je PR Titel ook altijd dit formaat volgt!

## 3. Pull Requests (PR) Workflow

1. Push: Push je branch naar GitHub.
2. Open PR: Maak een Pull Request naar `main`.
3. Check: Zorg dat de CI/CD tests (GitHub Actions) groen zijn.
4. Review: Vraag minstens één teamlid om goedkeuring.
5. Merge: Gebruik "Squash and Merge".

---
*Bij twijfel over het type commit, raadpleeg de Conventional Commits specificatie.*
