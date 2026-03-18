# EasyLend Backend

TODO: Docker Compose setup documentation

## Database Migrations (Alembic)

We use **Alembic** to safely apply changes to our SQLAlchemy models (`models.py`) to the PostgreSQL database. This ensures that our database structure is always in sync with our code.

### 🚀 The 3 Key Commands

Make sure your terminal is in the `backend/api` directory and your Docker database is running before using these commands.

**1. Stage a new change (Autogenerate)**
Have you added a new table, column, or relationship in `models.py`? Let Alembic detect the differences and generate a migration script:

```bash
uv run alembic revision --autogenerate -m "Short description of your change"

```

*(Always inspect the generated file in `alembic/versions/` to verify that Alembic interpreted everything correctly!)*

**2. Apply the change to the database (Upgrade)**
Once your script is ready (or after pulling a colleague's code), run this command to actually update the database:

```bash
uv run alembic upgrade head

```

**3. Undo a mistake (Downgrade)**
Have you accidentally applied a bad migration to your local database? You can roll back one step with:

```bash
uv run alembic downgrade -1

```

*(Note: In PostgreSQL, `Enum` types are sometimes not automatically removed during a downgrade. When setting up a completely fresh local environment, it can be faster to reset your Docker container with `docker compose down -v`).*
