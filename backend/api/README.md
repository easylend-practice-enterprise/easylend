# EasyLend API (FastAPI)

## Run The Correct Dev Server

Use this command from `backend/api`:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir .
```

Important:

- Do not run `uvicorn main:app` for the API service.
- `main:app` is used by the Vision service in `backend/vision/main.py` and does not expose `/api/v1/catalog`.

## Quick Verification

After startup:

- Open `http://127.0.0.1:8000/docs` and verify the API title is `EasyLend API`.
- Check that `GET /api/v1/catalog` appears under tag `catalog`.

If you do not see those routes, you are likely running a different service/module target.

## Localhost Caveat (Windows + Docker/WSL)

On some Windows setups, `localhost` resolves to IPv6 (`::1`) and can hit a different listener than your local uvicorn process.

- `127.0.0.1:8000` -> your API uvicorn process (contains `/api/v1/catalog`)
- `localhost:8000` or `[::1]:8000` -> may hit Docker/WSL relay (can show a different OpenAPI)

If Swagger looks inconsistent, always verify against `http://127.0.0.1:8000/openapi.json`.
