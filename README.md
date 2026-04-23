# WeekUp Vercel + Postgres Ready

## What changed

This version uses PostgreSQL through SQLAlchemy instead of in-memory Python dictionaries.
That means users, challenges, members, entries, invites, and sync sources persist after redeploys.

## Repo structure

- `index.html` — Telegram Mini App frontend
- `api/index.py` — FastAPI API entrypoint for Vercel
- `app/database.py` — database engine and session
- `app/models.py` — SQLAlchemy models
- `app/schemas.py` — request schemas
- `requirements.txt` — Python dependencies
- `vercel.json` — Vercel routing config
- `.env.example` — required environment variables

## Vercel setup

1. Create a Postgres database, either Vercel Postgres or any external PostgreSQL provider.
2. Copy the connection string into `POSTGRES_URL` in Vercel Environment Variables.
3. Push this repo to GitHub.
4. Redeploy in Vercel.

## Important notes

- Table creation currently runs automatically on startup via `Base.metadata.create_all(bind=engine)`.
- For real production later, replace that with Alembic migrations.
- Telegram initData verification is still not implemented yet.

## Main endpoints

- `POST /api/auth/telegram`
- `POST /api/challenges`
- `GET /api/challenges/{id}`
- `GET /api/invites/{code}`
- `POST /api/invites/{code}/accept`
- `POST /api/challenges/{id}/entries/manual`
- `POST /api/sync/connect`
- `POST /api/sync/import`
- `GET /api/challenges/{id}/leaderboard`
- `POST /api/challenges/{id}/finalize`
