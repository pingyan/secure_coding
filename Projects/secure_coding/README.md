# Agent Identity Management System (AIMS)

Identity lifecycle management for AI/LLM agents. Handles registration, authentication (API keys + JWT), capability-based authorization, key rotation, suspension/revocation, and audit logging.

Built with Python, FastAPI, SQLAlchemy, and SQLite.

## Quick Start

```bash
pip install -r requirements.txt
python seed.py          # Creates admin agent + API key (save the key!)
uvicorn main:app --reload
```

Open http://localhost:8000/docs for the Swagger UI.

## Authentication Flow

1. **Bootstrap** - `python seed.py` creates the admin agent and prints a raw API key
2. **Key → JWT** - Exchange the API key for a short-lived JWT:
   ```bash
   curl -X POST http://localhost:8000/auth/token -H "X-API-Key: aims_..."
   ```
3. **Use JWT** - Pass the token on all other endpoints:
   ```bash
   curl http://localhost:8000/agents -H "Authorization: Bearer <jwt>"
   ```

## API Endpoints

### Authentication
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/token` | X-API-Key | Exchange API key for JWT |

### Agents
| Method | Path | Capability | Description |
|--------|------|------------|-------------|
| POST | `/agents` | `agents:write` | Register agent |
| GET | `/agents` | `agents:read` | List agents |
| GET | `/agents/{id}` | `agents:read` | Get agent |
| PATCH | `/agents/{id}` | `agents:write` | Update agent |
| POST | `/agents/{id}/suspend` | `admin:*` | Suspend agent |
| POST | `/agents/{id}/reactivate` | `admin:*` | Reactivate agent |
| POST | `/agents/{id}/revoke` | `admin:*` | Revoke agent (irreversible) |
| DELETE | `/agents/{id}` | `admin:*` | Delete agent |

### API Keys
| Method | Path | Capability | Description |
|--------|------|------------|-------------|
| POST | `/agents/{id}/keys` | `keys:manage` | Create key (raw key shown once) |
| GET | `/agents/{id}/keys` | `keys:manage` | List keys |
| POST | `/agents/{id}/keys/{key_id}/rotate` | `keys:manage` | Rotate with grace period |
| DELETE | `/agents/{id}/keys/{key_id}` | `keys:manage` | Revoke key |

### Capabilities
| Method | Path | Capability | Description |
|--------|------|------------|-------------|
| POST | `/capabilities` | `admin:*` | Create capability |
| GET | `/capabilities` | `agents:read` | List capabilities |
| POST | `/agents/{id}/capabilities` | `admin:*` | Grant capability |
| DELETE | `/agents/{id}/capabilities/{cap_id}` | `admin:*` | Revoke capability |

### Audit & Health
| Method | Path | Capability | Description |
|--------|------|------------|-------------|
| GET | `/audit` | `audit:read` | Query audit logs |
| GET | `/_health` | None | Health check |

## Security Features

- **API keys hashed with SHA-256** - raw key shown only at creation
- **No self-elevation** - agents cannot modify their own capabilities or status
- **Cascade on revocation** - revoking an agent revokes all its API keys
- **Suspension checked at auth time** - suspended agents get 403 on token exchange
- **Key rotation grace period** - old key stays valid for 24h (configurable) after rotation
- **Rate limiting** - sliding window per IP on all endpoints
- **Audit trail** - every mutation logged with actor, action, timestamp, and details

## Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./aims.db` | Database connection string |
| `JWT_SECRET_KEY` | (change me) | Secret for signing JWTs |
| `JWT_EXPIRATION_MINUTES` | `30` | JWT lifetime |
| `KEY_ROTATION_GRACE_HOURS` | `24` | How long old keys stay valid after rotation |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `20` | Auth endpoint rate limit per IP |
| `RATE_LIMIT_API_PER_MINUTE` | `60` | API endpoint rate limit per IP |

## Tests

```bash
pytest tests/ -v
```

## Project Structure

```
├── main.py              # FastAPI app entry point
├── config.py            # Settings (pydantic-settings)
├── database.py          # SQLAlchemy engine/session
├── seed.py              # Bootstrap admin agent
├── models/              # ORM models (5 tables)
├── schemas/             # Pydantic request/response models
├── auth/                # Hashing, JWT, auth dependencies
├── routers/             # API route handlers
├── middleware/           # Rate limiting, request timing
└── tests/               # 42 tests
```
