# WeekUp · Telegram Mini App (RU/EN sporty dark)

WeekUp is a Telegram Mini App with a FastAPI backend and PostgreSQL persistence. This version ships a sporty dark mobile-first UI, bilingual RU/EN interface, and a full flow: create challenge → invite friends → auto-join via deep link → live leaderboard.

## Files to place in your repo

- `index.html` — frontend, use the new RU/EN sporty dark file from this package
- `api/index.py` — backend, use the provided `index-9.py` as `api/index.py`
- `vercel.json` — Vercel config from this package
- `.env.example` — environment variable template from this package

## Environment variables

Set these in Vercel Project Settings → Environment Variables:

- `POSTGRES_URL` — PostgreSQL connection string
- `TELEGRAM_BOT_TOKEN` — your bot token from BotFather
- `TELEGRAM_WEBAPP_URL` — deployed public URL of the mini app (e.g. `https://your-project.vercel.app`)
- `TELEGRAM_BOT_USERNAME` — bot username without `@` (e.g. `weekupbot`)
- `APP_ENV` — `production`

## Frontend behavior (index.html)

- RU/EN UI toggle in the top bar; language also auto-picked from Telegram user `language_code`.
- Home screen: active challenge summary (rank, today, gap to leader, days left) and a big CTA to add result.
- Board screen: live leaderboard and challenge status cards (mode, trust, players count, duration, totals).
- Invite screen: invite link from backend (`https://t.me/your_bot?startapp=CODE`), copy and Telegram share buttons.
- Create screen: simple form to start a new challenge (name, type, mode, max players, duration).
- Profile screen: Telegram name/username/language/timezone surfaced from `/api/auth/telegram`.

All screens are optimized for Telegram Mini Apps on mobile: one primary action per screen, sticky bottom navigation, and short scroll.

## Backend API used by the frontend

`index.html` expects the following endpoints (all already implemented in `index-9.py`):

- `POST /api/auth/telegram` — create/update user by Telegram ID and return `user.id`.
- `POST /api/challenges` — create challenge and return `challenge` + `invite_link`.
- `GET /api/challenges/{challenge_id}` — return `challenge`, `summary`, and `leaderboard` for the Home/Board screens.
- `GET /api/challenges/{challenge_id}/leaderboard` — not called directly now, but available for future use.
- `GET /api/invites/{code}` — resolve invite `CODE` to a challenge and its meta; used when Mini App is opened via `startapp=CODE`.
- `POST /api/invites/{code}/accept` — join the challenge by invite code for the current user.
- `POST /api/challenges/{challenge_id}/entries/manual` — add manual entry for today and refresh summary + leaderboard.

## Deep link / invite behavior

- When a user creates a challenge, backend returns `invite_link` like `https://t.me/your_bot?startapp=CODE`.
- On the Invite screen, the app shows this link, can copy it to clipboard, and can open Telegram share with pre-filled text.
- When a friend opens the bot via that link and starts the Mini App, Telegram passes the `CODE` as `start_param` to the Web App.
- `index.html` reads `start_param`, calls `GET /api/invites/{code}` and then `POST /api/invites/{code}/accept` for the current Telegram user.
- After joining, the app loads the challenge and shows the Home/Board screens for this challenge.

## Deploy checklist

1. Put the frontend file in the repo root as `index.html` (replace the old prototype file).
2. Put the backend file in `api/index.py` using the provided `index-9.py`.
3. Add `vercel.json` to the repo root.
4. Add the environment variables in Vercel.
5. Set up your Telegram bot to open the Mini App and use links of the form `https://t.me/your_bot?startapp=CODE` for invites.
6. Redeploy the Vercel project.

## What now works

- RU/EN sporty dark Telegram Mini App UI.
- Dynamic leaderboard from backend data.
- Telegram usernames in leaderboard when users have opened the mini app.
- Invite deep-link handling via `startapp=CODE` and auto-join to the active challenge.
- Real challenge refresh after create, join and manual entry.

## Important note

Telegram `initData` verification is still not implemented in this package. For production security, add server-side verification before treating Telegram identity as trusted.
