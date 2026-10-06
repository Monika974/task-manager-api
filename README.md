# Task Manager API

A REST API for managing personal tasks, with JWT authentication. Each user can only see and modify their own tasks.

**Stack:** Python 3.10+ · FastAPI · SQLAlchemy 2 · SQLite (default) or PostgreSQL · JWT (PyJWT) · bcrypt

## Features

- Register / login with **bcrypt**-hashed passwords and **JWT** bearer tokens
- Full task CRUD, scoped to the logged-in user (other users' tasks return `404`)
- Pagination plus optional `status` / `priority` filters on the list endpoint
- Input validation on every endpoint and uniform JSON error responses
- Auto-generated **Swagger UI** (`/docs`), ReDoc (`/redoc`), and a **Postman collection**
- 14 automated tests (pytest)

## Project structure

```
app/
  main.py          # app setup, startup, global error handlers
  config.py        # settings loaded from env / .env
  database.py      # engine, session, get_db dependency
  models.py        # User and Task tables
  schemas.py       # request/response validation (Pydantic)
  security.py      # password hashing, JWT create/decode
  deps.py          # get_current_user (auth dependency)
  routers/
    auth.py        # /api/auth/*
    tasks.py       # /api/tasks/*
tests/test_api.py  # pytest suite
postman_collection.json
```

## Setup

```bash
git clone <your-repo-url>
cd task-manager-api

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then set SECRET_KEY to a long random string
```

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

### Database

- **SQLite (default):** nothing to do. `tasks.db` is created on first run.
- **PostgreSQL:** create a database, then set in `.env`:
  `DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/taskdb`

Tables are created automatically on startup.

## Run

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

## Run tests

```bash
pytest
```

## Database schema

**users**: `id` (PK), `name`, `email` (unique, indexed), `password_hash`, `created_at`

**tasks**: `id` (PK), `title`, `description` (nullable), `status` (`pending` | `in_progress` | `completed`), `priority` (`low` | `medium` | `high`), `created_at`, `updated_at`, `user_id` (FK -> users.id, indexed, `ON DELETE CASCADE`)

## API documentation

All task endpoints require the header `Authorization: Bearer <token>`.

### Auth

#### `POST /api/auth/register` → `201`
```json
{ "name": "Alice", "email": "alice@example.com", "password": "password123" }
```
Rules: name 1–100 chars; valid email; password 8–72 bytes.
Response:
```json
{ "id": 1, "name": "Alice", "email": "alice@example.com", "created_at": "2026-10-06T13:01:49" }
```
Errors: `400` validation, `409` email already registered.

#### `POST /api/auth/login` → `200`
```json
{ "email": "alice@example.com", "password": "password123" }
```
Response:
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```
Errors: `400` validation, `401` wrong email or password.

### Tasks

| Method | Path | Description | Success |
|---|---|---|---|
| POST | `/api/tasks` | Create a task | `201` |
| GET | `/api/tasks` | List your tasks (paginated) | `200` |
| GET | `/api/tasks/{id}` | Get one task | `200` |
| PUT | `/api/tasks/{id}` | Update a task | `200` |
| DELETE | `/api/tasks/{id}` | Delete a task | `200` |

#### `POST /api/tasks`
```json
{ "title": "Write README", "description": "optional", "status": "pending", "priority": "high" }
```
`title` is required (1–200 chars, not blank). `status` defaults to `pending`, `priority` to `medium`.

#### `GET /api/tasks`
Query params: `page` (default 1), `page_size` (default 10, max 100), `status`, `priority`. Newest first.
```json
{
  "items": [ { "id": 3, "title": "...", "description": null, "status": "pending",
               "priority": "medium", "created_at": "...", "updated_at": "..." } ],
  "page": 1, "page_size": 10, "total": 25, "total_pages": 3
}
```

#### `PUT /api/tasks/{id}`
`title` is required; `description`, `status`, `priority` are updated only if included in the body.

#### `DELETE /api/tasks/{id}`
```json
{ "message": "Task 3 deleted" }
```

### Error format

```json
{ "error": "Task 999 not found" }
```
Validation errors include per-field details:
```json
{ "error": "Validation failed",
  "details": [ { "field": "title", "message": "String should have at least 1 character" } ] }
```

| Code | Meaning |
|---|---|
| 200 / 201 | Success / created |
| 400 | Validation failed (bad body, query param, or path param) |
| 401 | Missing, invalid, or expired token; bad login |
| 404 | Task not found (or belongs to another user) |
| 409 | Email already registered |
| 500 | Unexpected server error (details are logged, not exposed) |

## Postman

Import `postman_collection.json`. Run **Register → Login** (the token is saved automatically), then the Tasks requests. `baseUrl` defaults to `http://localhost:8000`.

## Design notes

- **Authorization:** every task query filters by `user_id`, and accessing another user's task returns `404` rather than `403` so task IDs can't be probed.
- **Passwords:** hashed with bcrypt (per-password salt); never returned by the API.
- **Login errors** are identical for unknown email and wrong password to avoid account enumeration.
- **Emails** are lowercased so `A@x.com` and `a@x.com` are the same account.
