# Backend — Auth template

FastAPI app with authentication only: register, login, email verification, password reset. PostgreSQL for data; no S3 or MinIO required to run.

## Tech stack

- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) with asyncpg
- Alembic for migrations
- uv for dependency management

## Requirements

- Python 3.13 (`uv`)
- PostgreSQL 15+ (or 18 in Docker)

## Quick start

### With Docker Compose

```bash
cd ..
docker compose up --build backend db
```

### Locally

```bash
cd backend
uv sync
cp .env.example .env   # set DB_* and optionally RESEND_API_KEY
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

## Environment variables

| Variable | Description |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | PostgreSQL connection |
| `RESEND_API_KEY` | Optional; required for email verification and password reset |
| `APP_NAME`, `APP_VERSION`, `DEBUG` | App metadata and debug flag |

See `.env.example` for defaults. Use `.env` at backend root; pydantic-settings loads it.

## Project structure

```
backend/app/
├── api/v1/routes/   # auth, ping
├── api/v1/schemas/  # auth schemas
├── core/            # config, dependencies, security, logger
├── db/models/       # User, Session, EmailVerificationToken, PasswordResetToken
├── db/session.py    # async engine and get_db_session
├── templates/       # email templates (verification, password reset)
└── main.py
```

## Commands

- `uv sync` — install dependencies
- `uv run uvicorn app.main:app --reload` — run API
- `uv run alembic revision --autogenerate -m "message"` — create migration
- `uv run alembic upgrade head` — apply migrations
- `uv run pytest` — run tests

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/ping` | Health check + DB check |
| POST | `/auth/register` | Register |
| POST | `/auth/login` | Login (sets cookie) |
| POST | `/auth/token/refresh` | Refresh access token |
| POST | `/auth/logout` | Logout |
| GET | `/auth/me` | Current user (protected) |
| POST | `/auth/verify-email` | Verify email (token) |
| POST | `/auth/forgot-password` | Request password reset email |
| POST | `/auth/reset-password` | Reset password (token) |

## Troubleshooting

- **DB connection failed**: check PostgreSQL is running and `.env` credentials.
- **Dependency issues**: run `uv sync` after changing `pyproject.toml`.
