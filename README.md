# WeekUp Vercel + Postgres Ready

WeekUp is a Telegram Mini App with a FastAPI backend and PostgreSQL persistence. This package includes a dynamic leaderboard, Telegram username display for joined members, invite deep-link auto-join flow, and Vercel-ready routing.

## Files to place in your repo

- `index.html` — frontend, use the provided updated `index-2.html` file and rename it to `index.html`
- `api/index.py` — backend, use the provided updated `index.py`
- `vercel.json` — Vercel config from this package
- `.env.example` — environment variable template from this package

## Environment variables

Set these in Vercel Project Settings → Environment Variables:

- `POSTGRES_URL` — PostgreSQL connection string
- `TELEGRAM_BOT_TOKEN` — your bot token from BotFather
- `TELEGRAM_WEBAPP_URL` — deployed public URL of the mini app
- `TELEGRAM_BOT_USERNAME` — bot username without `@`
- `APP_ENV` — `production`

## Deploy checklist

1. Put the frontend file in the repo root as `index.html`.
2. Put the backend file in `api/index.py`.
3. Add `vercel.json` to the repo root.
4. Add the environment variables in Vercel.
5. Redeploy.

## What now works

- Dynamic leaderboard from backend data
- Telegram usernames in leaderboard when users have opened the mini app
- Invite deep-link handling via `startapp=CODE`
- Auto-accept invite after Telegram auth
- Real challenge refresh after create, join, manual entry, and sync import

## Important note

Telegram `initData` verification is still not implemented in this package. For production security, add server-side verification before treating Telegram identity as trusted.
