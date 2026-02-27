# EasyLend Backend

TODO: docker compose uitleg

## Database Migraties (Alembic)

Wij gebruiken **Alembic** om wijzigingen in onze SQLAlchemy modellen (`models.py`) veilig door te voeren naar de PostgreSQL database. Dit zorgt ervoor dat onze database-structuur altijd in sync is met onze code.

### 🚀 De 3 Sleutelcommando's

Zorg dat je terminal in de `backend/api` map staat en je Docker database draait voordat je deze commando's gebruikt.

**1. Een nieuwe wijziging klaarzetten (Autogenerate)**
Heb je een nieuwe tabel, kolom of relatie toegevoegd in `models.py`? Laat Alembic dan de verschillen zoeken en een migratie-script genereren:

```bash
uv run alembic revision --autogenerate -m "Korte beschrijving van je wijziging"

```

*(Controleer altijd even het gegenereerde bestand in `alembic/versions/` of Alembic alles goed heeft begrepen!)*

**2. De wijziging doorvoeren naar de database (Upgrade)**
Zodra je script klaar staat (of als je de code van een collega hebt gepulld), voer je dit commando uit om de database daadwerkelijk bij te werken:

```bash
uv run alembic upgrade head

```

**3. Een foutje ongedaan maken (Downgrade)**
Heb je per ongeluk een foute migratie doorgevoerd op je lokale database? Je kunt één stap terug in de tijd met:

```bash
uv run alembic downgrade -1

```

*(Let op: Bij PostgreSQL worden `Enum` types soms niet automatisch verwijderd bij een downgrade. Bij het lokaal opzetten van een compleet nieuwe architectuur is het soms sneller om je Docker container even te resetten met `docker compose down -v`).*
