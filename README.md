# Relohelp — Auth template

A minimal full-stack template with **authentication only**: register, login, email verification, password reset. Use it as a starting point for new projects.

## What we are building 
https://www.notion.so/MVP-description-and-App-Architecture-3055ee5a340e80729cacc041f45b513c

## Stack

- **Frontend**: React 19, TypeScript, Vite, React Router, shadcn/ui, Tailwind. Auth via cookies (access + refresh tokens).
- **Backend**: FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL. User model, sessions, email verification and password reset tokens.
- **Infrastructure**: PostgreSQL; Docker Compose to run the full stack. Optional: Resend for emails (verification + password reset).

## Modules
### telegram_scrapper
#### First run
```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
source .venv/bin/activate
```
### Run single chat 
```bash
python export.py 1350470024 --limit 1500 --append -o ./my_export.csv
```
### Run multiple chats 
```bash
python -m telegram_scrapper.batch_export \
  --limit 1500 \
  --sleep-between-chats 10 \
  --since-days 180 \
  -o telegram_scrapper/merged.csv 
```

Per chat, effective row cap is `min(--limit, number_of_messages in chats.json)` when both are set. Logs: `telegram_scrapper/logging.ini` -> console + `telegram_scrapper/logs/log.log`. With `--since-days`, check logs for the computed equivalent `--until-date` (UTC calendar day).


### Check validity of csv
```bash
python3 check_scv_readability.py
```

Traceback (most recent call last):


## Setup

### 1. Run with Docker Compose

Prerequisites: Docker (24+) and Docker Compose Plugin (v2).

```bash
cp backend/.env.example backend/.env
# Optional: set RESEND_API_KEY in backend/.env for email (verification, password reset)

docker compose up --build
```

Runs backend (port 8000), frontend (Nginx), and PostgreSQL. Migrations run on backend startup.

### 2. Run locally

**Backend**

```bash
cd backend
uv sync
cp .env.example .env   # set DB_* and optionally RESEND_API_KEY
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

You need PostgreSQL 15+ (or 18) with DB/user matching `backend/.env`.

## Requirements

- **Backend**: Python 3.13, `uv`, PostgreSQL 15+.
- **Frontend**: Node.js 20+, npm.
- **Optional**: Resend API key for email verification and password reset.

## Features (included)

- User registration and login (cookie-based access + refresh tokens).
- Email verification (optional, requires Resend).
- Forgot password / reset password (optional, requires Resend).
- Protected routes and simple dashboard placeholder.
- Health check: `GET /ping`.

## Git

Use short-lived feature branches from `main` and open PRs for changes.
